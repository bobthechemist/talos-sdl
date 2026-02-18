# host/ai/agent_executor.py
import time
import json
import os
import queue
from datetime import datetime
from host.gui.console import C
from shared_lib.messages import Message
from host.core.registry import Registry
from host.ai.llm_manager import LLMManager

class AgentExecutor:
    def __init__(self, manager, device_ports, agent, planner, plate_manager, require_confirmation=True):
        self.manager = manager
        self.device_ports = device_ports
        self.agent = agent
        self.planner = planner
        self.plate_manager = plate_manager
        self.registry = Registry()
        self.total_tokens = 0
        self.session_history = []
        self.require_confirmation = require_confirmation

    def run(self, goal, max_turns=5):
        # Initialize session history for a new user goal if it's the first turn
        if not self.session_history:
            self.session_history.append({
                "timestamp": datetime.now().isoformat(),
                "event": "session_start",
                "system_context": self.planner.build_system_context(),
                "world_model": self.planner.world_model
            })

        self.session_history.append({
            "timestamp": datetime.now().isoformat(),
            "event": "new_goal",
            "goal": goal
        })
        
        observation = None
        
        # This loop represents "AI Turns" (Planning attempts)
        for i in range(max_turns):
            # ... (Prompt building logic remains similar) ...
            plate_summary = self.plate_manager.get_plate_summary()
            prompt = self.planner.build_user_prompt(goal, plate_summary, observation)
            
            print(f"[*] Thinking...")
            response = self.agent.prompt(prompt, use_history=True)
            
            if response is None:
                print(f"{C.ERR}[Agent] Critical: The AI provider failed to return a response.{C.END}")
                break

            usage = self.agent.last_run_info
            self.total_tokens += usage.get('total_tokens', 0)
            
            turn_log = {
                "turn": i + 1,
                "timestamp": datetime.now().isoformat(),
                "prompt_sent": prompt,
                "response_raw": response,
                "usage": usage
            }

            # --- Parse AI Response ---
            try:
                json_str = response
                if "```json" in response:
                    json_str = response.split("```json")[1].split("```")[0]
                elif "```" in response:
                    json_str = response.split("```")[1].split("```")[0]
                
                ai_data = json.loads(json_str.strip())
                turn_log["parsed_data"] = ai_data
            except Exception as e:
                print(f"{C.WARN}[Agent] Message: {response.strip()}{C.END}")
                turn_log["error"] = "JSON Parse Error - Text Response Recieved"
                turn_log["raw_text"] = response
                self.session_history.append(turn_log)
                return True

            # --- Check for Completion ---
            if ai_data.get("status") == "COMPLETE":
                print(f"\n{C.OK}[Agent] {ai_data.get('message')}{C.END}")
                turn_log["event"] = "task_complete"
                self.session_history.append(turn_log)
                return True

            # --- Extract Plan ---
            plan = ai_data.get("plan", [])
            if not isinstance(plan, list):
                plan = [ai_data]

            # --- PLAN REVIEW & EDITING ---
            if self.require_confirmation:
                plan = self._review_and_edit_plan(plan)
                if plan is None:
                    print(f"{C.ERR}Plan rejected by human.{C.END}")
                    observation = "ERROR: Human operator rejected the plan. Ask what they want to change."
                    turn_log["status"] = "REJECTED_BY_HUMAN"
                    self.session_history.append(turn_log)
                    continue 
                if not plan:
                    print(f"{C.WARN}Plan is empty. Returning control to AI.{C.END}")
                    observation = "WARNING: The human cleared the plan. No actions were taken."
                    continue

            # --- BATCH EXECUTION ---
            execution_success = True
            failed_step = None
            step_results = []
            
            print(f"\n{C.INFO}Executing Plan...{C.END}")
            for step_idx, step in enumerate(plan):
                device = step.get("device", "").lower()
                command = step.get("command")
                args = step.get("args", {})
                port = self.device_ports.get(device)

                print(f"  -> Step {step_idx+1}/{len(plan)}: {device} {command}...", end="", flush=True)

                if not port:
                    print(f" {C.ERR}[FAILED]{C.END} (Device not found)")
                    execution_success = False
                    failed_step = f"Step {step_idx+1}: Device '{device}' not connected."
                    break

                # Send Command
                instruction_msg = Message.create_message(
                    subsystem_name="AGENT_EXECUTOR", 
                    status="INSTRUCTION", 
                    payload={"func": command, "args": args}
                )
                self.manager.send_message(port, instruction_msg) 
                
                # Wait for Result
                result = self._wait_for_result(port)
                
                step_results.append(result)

                if result['status'] in ("SUCCESS", "DATA_RESPONSE"):
                    print(f" {C.OK}[OK]{C.END}")
                    
                    if result['status'] == "DATA_RESPONSE":
                        # --- DATA HANDLING ---
                        payload = result['payload']
                        
                        # 1. Register Data
                        ds_id, entry = self.registry.register(device, command, payload)
                        print(f"     {C.OK}[Registry] Saved as {ds_id} ({entry['files']}){C.END}")
                        
                        # 2. One-Shot Analysis
                        self._perform_one_shot_analysis(goal, device, payload)

                        # Update observation for the NEXT turn
                        # We don't feed the raw big data back to the main agent, just the ID and summary
                        # (Ideally the one-shot summary would be captured here, but for now we print it)
                    
                    # Update plate memory
                    if command in ('dispense', 'dispense_at', 'to_well'):
                        self._update_plate_memory(args)
                else:
                    print(f" {C.ERR}[PROBLEM]{C.END}")
                    print(f"     Details: {result['payload']}")
                    execution_success = False
                    failed_step = f"Step {step_idx+1} ({command}) failed: {result['payload']}"
                    break
            
            turn_log["step_results"] = step_results
            
            if execution_success:
                print(f"{C.OK}[Agent] Plan executed successfully.{C.END}")
                turn_log["execution_result"] = "Success"
                self.session_history.append(turn_log)
                return True 
            else:
                print(f"{C.ERR}[Agent] Plan aborted due to error.{C.END}")
                observation = f"EXECUTION FAILED: {failed_step}"
                turn_log["execution_result"] = f"Failed: {failed_step}"
                self.session_history.append(turn_log)
                # Loop continues to let Agent retry based on error

        return False

    def _perform_one_shot_analysis(self, user_goal, device, data_payload):
        """
        Spins up a temporary agent to interpret the data immediately.
        """
        print(f"     {C.INFO}[Analysis] Interpreting results...{C.END}")
        
        # Construct the context for the analyst
        guidance = self.planner.guidance_dict.get(device, "No specific guidance available.")
        
        system_prompt = (
            "You are a Scientific Data Analyst. "
            "Your job is to interpret raw instrument data in the context of the user's goal. "
            "Be concise. Identify peaks, trends, or specific values relevant to the goal. "
            "Do not describe the JSON structure, describe the Chemistry/Physics."
        )
        
        user_prompt = (
            f"User Goal: {user_goal}\n"
            f"Instrument: {device}\n"
            f"Firmware Guidance: {guidance}\n"
            f"Captured Data: {json.dumps(data_payload, indent=2)}\n\n"
            "Interpret this data."
        )

        try:
            # Create a throwaway agent
            # We assume LLMManager is configured via environment variables
            analyst = LLMManager.get_agent(context=system_prompt) 
            summary = analyst.prompt(user_prompt, use_history=False)
            
            print(f"\n{C.INFO}--- ONE-SHOT ANALYSIS ---{C.END}")
            print(f"{summary}")
            print(f"{C.INFO}-------------------------{C.END}\n")
            
            # Log this? Ideally yes, but sticking to basics for M1
        except Exception as e:
            print(f"{C.ERR}     [Analysis Failed] {e}{C.END}")

    def _review_and_edit_plan(self, plan):
        # ... (Existing implementation unchanged) ...
        return plan

    def _update_plate_memory(self, args):
        # ... (Existing implementation unchanged) ...
        well = args.get('well') or args.get('to_well')
        pump = args.get('pump')
        vol = args.get('vol', 0)
        if well and pump and vol > 0:
            self.plate_manager.add_liquid(well, pump, vol)

    def _wait_for_result(self, port, timeout=60):
        # ... (Existing implementation unchanged) ...
        start = time.time()
        while time.time() - start < timeout:
            try:
                msg_type, msg_port, msg_data = self.manager.incoming_message_queue.get(timeout=1)
                if msg_port == port and msg_type == 'RECV':
                    status = msg_data.status
                    if status in ("SUCCESS", "PROBLEM", "DATA_RESPONSE"):
                        return {"status": status, "payload": msg_data.payload}
            except queue.Empty:
                continue
        return {"status": "ERROR", "payload": "Hardware timeout."}

    def save_log(self):
        # ... (Existing implementation unchanged) ...
        if not self.session_history: return
        if not os.path.exists("temp"): os.makedirs("temp")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"temp/chat-session-{timestamp}.json"
        try:
            with open(filename, 'w') as f:
                json.dump(self.session_history, f, indent=2)
            print(f"\n{C.INFO}[Log] Session saved: {filename}{C.END}")
        except Exception as e:
            print(f"{C.ERR}Failed to save log: {e}{C.END}")