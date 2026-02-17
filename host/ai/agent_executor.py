# host/ai/agent_executor.py
import time
import json
import os
import queue
from datetime import datetime
from host.gui.console import C
from shared_lib.messages import Message

class AgentExecutor:
    def __init__(self, manager, device_ports, agent, planner, plate_manager, require_confirmation=True):
        self.manager = manager
        self.device_ports = device_ports
        self.agent = agent
        self.planner = planner
        self.plate_manager = plate_manager
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
            plate_summary = self.plate_manager.get_plate_summary()
            prompt = self.planner.build_user_prompt(goal, plate_summary, observation)
            
            print(f"[*] Thinking...")
            response = self.agent.prompt(prompt, use_history=True)
            
            if response is None:
                print(f"{C.ERR}[Agent] Critical: The AI provider failed to return a response.{C.END}")
                break

            usage = self.agent.last_run_info
            self.total_tokens += usage['total_tokens']
            
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
                # --- FIX IS HERE: Gracefully handle non-JSON text responses ---
                print(f"{C.WARN}[Agent] Message: {response.strip()}{C.END}")
                turn_log["error"] = "JSON Parse Error - Text Response Recieved"
                turn_log["raw_text"] = response
                self.session_history.append(turn_log)
                # Treat a text response as a completion/refusal and return to user
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
                    failed_step = f"Step {step_idx+1} ({command}): Device '{device}' not connected."
                    step_results.append({
                        "step": step_idx + 1,
                        "device": device,
                        "command": command,
                        "status": "FAILED",
                        "error": "Device not connected"
                    })
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
                
                step_results.append({
                    "step": step_idx + 1,
                    "device": device,
                    "command": command,
                    "args": args,
                    "status": result['status'],
                    "payload": result['payload']
                })

                if result['status'] in ("SUCCESS", "DATA_RESPONSE"):
                    print(f" {C.OK}[OK]{C.END}")
                    
                    if result['status'] == "DATA_RESPONSE":
                        payload = result['payload']
                        display_data = payload.get('data', payload)
                        formatted_data = json.dumps(display_data, indent=2)
                        formatted_data = formatted_data.replace('\n', '\n     ')
                        print(f"{C.INFO}     [DATA]: {formatted_data}{C.END}")

                    if command in ('dispense', 'dispense_at', 'to_well'):
                        self._update_plate_memory(args)
                else:
                    print(f" {C.ERR}[PROBLEM]{C.END}")
                    print(f"     Details: {result['payload']}")
                    execution_success = False
                    failed_step = f"Step {step_idx+1} ({command}) failed: {result['payload']}"
                    break
            
            # --- FINAL RESULT HANDLING ---
            turn_log["step_results"] = step_results
            
            if execution_success:
                print(f"{C.OK}[Agent] Plan executed successfully.{C.END}")
                turn_log["execution_result"] = "Success"
                self.session_history.append(turn_log)
                return True 
            else:
                print(f"{C.ERR}[Agent] Plan aborted due to error.{C.END}")
                turn_log["execution_result"] = f"Failed: {failed_step}"
                self.session_history.append(turn_log)
                return False 

        return False

    def _review_and_edit_plan(self, plan):
        """
        Interactive loop allowing the user to view, edit, or reject the plan.
        Returns the modified plan (list) or None if rejected.
        """
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

    def _update_plate_memory(self, args):
        """Helper to update plate manager based on command args."""
        well = args.get('well') or args.get('to_well')
        pump = args.get('pump')
        vol = args.get('vol', 0)
        if well and pump and vol > 0:
            self.plate_manager.add_liquid(well, pump, vol)

    def _wait_for_result(self, port, timeout=60):
        """Polls the DeviceManager queue for a response from the specific port."""
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
        """Saves the current session history to the temp/ directory."""
        if not self.session_history:
            return

        if not os.path.exists("temp"):
            os.makedirs("temp")
            
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"temp/chat-session-{timestamp}.json"
        
        try:
            with open(filename, 'w') as f:
                json.dump(self.session_history, f, indent=2)
            print(f"\n{C.INFO}[Log] Session saved: {filename}{C.END}")
        except Exception as e:
            print(f"{C.ERR}Failed to save log: {e}{C.END}")