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
        
        # --- Context Memory ---
        self.last_known_well = "Unknown"
        self.last_failed_plan = None 

    def run(self, goal, max_turns=3):
        # Initialize session history
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
        self.last_failed_plan = None
        
        for i in range(max_turns):
            plate_summary = self.plate_manager.get_plate_summary()
            
            prompt = self.planner.build_user_prompt(
                goal, 
                plate_summary, 
                current_well=self.last_known_well, 
                observation=observation
            )
            
            print(f"[*] Thinking... (Turn {i+1}/{max_turns})")
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

            # --- DUPLICATE PLAN SAFEGUARD ---
            if plan == self.last_failed_plan:
                print(f"{C.ERR}[Safeguard] Aborting: Agent generated the exact same failing plan.{C.END}")
                turn_log["status"] = "ABORT_INFINITE_LOOP"
                self.session_history.append(turn_log)
                return False

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
            
            # --- NEW: Data Buffer for this Plan ---
            collected_data = [] 
            
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
                    step_results.append({
                        "step": step_idx + 1,
                        "status": "FAILED",
                        "error": "Device not connected"
                    })
                    break

                instruction_msg = Message.create_message(
                    subsystem_name="AGENT_EXECUTOR", 
                    status="INSTRUCTION", 
                    payload={"func": command, "args": args}
                )
                self.manager.send_message(port, instruction_msg) 
                
                result = self._wait_for_result(port)
                step_results.append(result)

                if result['status'] in ("SUCCESS", "DATA_RESPONSE"):
                    print(f" {C.OK}[OK]{C.END}")
                    
                    if result['status'] == "DATA_RESPONSE":
                        payload = result['payload']
                        ds_id, entry = self.registry.register(device, command, payload)
                        print(f"     {C.OK}[Registry] Saved as {ds_id} ({entry['files']}){C.END}")
                        
                        # --- NEW: Buffer data, do not analyze yet ---
                        collected_data.append({
                            "id": ds_id,
                            "device": device,
                            "command": command,
                            "args": args,
                            "payload": payload
                        })

                    self._update_executor_state(command, args)

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
                self.last_failed_plan = None 
                
                # --- NEW: Trigger Aggregated Analysis ---
                if collected_data:
                    self._perform_aggregated_analysis(goal, collected_data)
                
                return True 
            else:
                print(f"{C.ERR}[Agent] Plan aborted due to error.{C.END}")
                observation = f"EXECUTION FAILED: {failed_step}"
                turn_log["execution_result"] = f"Failed: {failed_step}"
                self.session_history.append(turn_log)
                self.last_failed_plan = plan

        return False

    def _perform_aggregated_analysis(self, user_goal, data_list):
        """
        Performs a One-Shot analysis on the COMPLETE set of data collected 
        during the plan execution.
        """
        print(f"\n{C.INFO}[Analysis] Aggregating results from {len(data_list)} datasets...{C.END}")
        
        # 1. Compile Unique Firmware Guidance
        # We only need guidance for the devices that actually produced data.
        relevant_devices = set(d['device'] for d in data_list)
        guidance_text = ""
        for dev in relevant_devices:
            text = self.planner.guidance_dict.get(dev, "")
            if text:
                guidance_text += f"[{dev.upper()} Guidance]: {text}\n"

        # 2. Compile Data Content
        data_summary = ""
        for item in data_list:
            # We strip out metadata from the payload to save context tokens, keeping the 'data' key
            core_data = item['payload'].get('data', item['payload'])
            
            data_summary += f"\n--- DATASET {item['id']} ---\n"
            data_summary += f"Source: {item['device']}.{item['command']}({item['args']})\n"
            data_summary += f"Content: {json.dumps(core_data, indent=None)}\n" # Compact JSON

        system_prompt = (
            "You are a Scientific Data Analyst. "
            "Your job is to interpret experimental results in the context of the user's goal. "
            "You have just completed a sequence of actions. Review the collected data collectively.\n"
            "- Identify trends, peaks, or relationships between the datasets.\n"
            "- Relate the findings directly back to the User Goal.\n"
            "- Be concise. Describe the chemistry/physics, not the JSON structure."
        )
        
        user_prompt = (
            f"User Goal: {user_goal}\n\n"
            f"Instrument Guidance:\n{guidance_text}\n"
            f"Collected Data:\n{data_summary}\n\n"
            "Analyze these results."
        )

        try:
            # Use a temporary analyst agent
            analyst = LLMManager.get_agent(context=system_prompt) 
            summary = analyst.prompt(user_prompt, use_history=False)
            
            print(f"\n{C.INFO}--- EXPERIMENT ANALYSIS ---{C.END}")
            print(f"{summary}")
            print(f"{C.INFO}---------------------------{C.END}\n")
            
            # Append analysis to history so the main agent "remembers" the result 
            # if we were to continue the conversation (though currently this method 
            # returns True immediately after, ending the turn).
            self.session_history.append({
                "event": "one_shot_analysis",
                "summary": summary
            })
            
        except Exception as e:
            print(f"{C.ERR}     [Analysis Failed] {e}{C.END}")

    def _review_and_edit_plan(self, plan):
        # ... (Existing implementation unchanged) ...
        while True:
            print(f"\n{C.WARN}--- PLAN REVIEW ---{C.END}")
            if not plan:
                print(f"  {C.ERR}(Plan is empty){C.END}")
            else:
                for idx, step in enumerate(plan):
                    dev = step.get('device', 'unknown').upper()
                    cmd = step.get('command', 'unknown')
                    args = json.dumps(step.get('args', {}))
                    print(f"  {C.INFO}{idx+1}.{C.END} {dev}: {cmd} {args}")

            print(f"\n{C.INFO}Commands: 'run' (or y), 'reject' (or n), 'del <#>', 'edit <#>'{C.END}")
            user_input = input(f"Action > ").strip()
            
            if user_input.lower() in ('run', 'y', 'yes'):
                return plan
            
            if user_input.lower() in ('reject', 'no', 'n'):
                return None
            
            parts = user_input.split()
            if len(parts) < 2:
                print(f"{C.ERR}Invalid command.{C.END}")
                continue
                
            action, target = parts[0].lower(), parts[1]
            
            try:
                idx = int(target) - 1
                if idx < 0 or idx >= len(plan):
                    print(f"{C.ERR}Invalid index.{C.END}")
                    continue
            except ValueError:
                print(f"{C.ERR}Target must be a number.{C.END}")
                continue

            if action == 'del':
                removed = plan.pop(idx)
                print(f"{C.WARN}Removed step {target}: {removed['command']}{C.END}")
            
            elif action == 'edit':
                step = plan[idx]
                print(f"{C.INFO}Editing Step {target}:{C.END} {step['device']} -> {step['command']}")
                print(f"Current Args: {json.dumps(step.get('args', {}))}")
                
                new_args_raw = input("Enter new args (JSON format) or 'c' to cancel: ").strip()
                if new_args_raw.lower() == 'c':
                    continue
                    
                try:
                    new_args = json.loads(new_args_raw)
                    if isinstance(new_args, dict):
                        plan[idx]['args'] = new_args
                        print(f"{C.OK}Step updated.{C.END}")
                    else:
                        print(f"{C.ERR}Args must be a JSON object (dictionary).{C.END}")
                except json.JSONDecodeError:
                    print(f"{C.ERR}Invalid JSON string.{C.END}")

    def _update_executor_state(self, command, args):
        """Updates internal memory of well position and plate contents."""
        if command in ('to_well', 'dispense_at', 'to_well_and_dispense'):
            well = args.get('well')
            if well:
                self.last_known_well = well.upper()
        
        if command in ('dispense', 'dispense_at', 'to_well_and_dispense'):
            well = args.get('well') or args.get('to_well') or self.last_known_well
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