# host/ai/agent_executor.py
import time
import json
import os
import queue
from datetime import datetime
from host.gui.console import C
from shared_lib.messages import Message
from host.ai.llm_manager import LLMManager

class AgentExecutor:
    def __init__(self, manager, device_ports, agent, planner, plate_manager, session_manager, require_confirmation=True):
        self.manager = manager
        self.device_ports = device_ports
        self.agent = agent
        self.planner = planner
        self.plate_manager = plate_manager
        self.session_manager = session_manager # DLN Session Manager
        self.total_tokens = 0
        self.require_confirmation = require_confirmation
        
        # --- Context Memory ---
        self.last_known_well = "Unknown"
        self.last_failed_plan = None 

    def run(self, goal, max_turns=3):
        """
        The main ReAct loop. Executes turns until the goal is met or max_turns is reached.
        Everything is logged to the Digital Lab Notebook via session_manager.
        """
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
            
            # --- DLN: Log the specific prompt for this turn ---
            current_entry_id = self.session_manager.log_event("prompt", {
                "turn": i + 1,
                "prompt_text": prompt,
                "current_well": self.last_known_well
            })

            print(f"[*] Thinking... (Turn {i+1}/{max_turns})")
            response = self.agent.prompt(prompt, use_history=True)
            
            if response is None:
                print(f"{C.ERR}[Agent] Critical: The AI provider failed to return a response.{C.END}")
                self.session_manager.log_event("error", {"detail": "AI Provider failed to respond"})
                break

            usage = self.agent.last_run_info
            self.total_tokens += usage.get('total_tokens', 0)
            
            # --- DLN: Log the raw response and token usage ---
            self.session_manager.log_event("ai_response", {
                "raw_text": response,
                "usage": usage
            })

            # --- Parse AI Response ---
            ai_data = None
            try:
                json_str = response
                if "```json" in response:
                    json_str = response.split("```json")[1].split("```")[0]
                elif "```" in response:
                    json_str = response.split("```")[1].split("```")[0]
                
                ai_data = json.loads(json_str.strip())
            except Exception as e:
                print(f"{C.WARN}[Agent] Message: {response.strip()}{C.END}")
                # Log as a natural language response / parse error
                self.session_manager.log_event("parse_error", {"raw_text": response, "error": str(e)})
                return True

            # --- Check for Completion ---
            if ai_data.get("status") == "COMPLETE":
                print(f"\n{C.OK}[Agent] {ai_data.get('message')}{C.END}")
                self.session_manager.log_event("task_complete", {"message": ai_data.get('message')})
                return True

            # --- Extract Plan ---
            plan = ai_data.get("plan", [])
            if not isinstance(plan, list):
                plan = [ai_data]

            # --- DUPLICATE PLAN SAFEGUARD ---
            if plan == self.last_failed_plan:
                print(f"{C.ERR}[Safeguard] Aborting: Agent generated the exact same failing plan.{C.END}")
                self.session_manager.log_event("abort", {"reason": "Infinite loop detected - plan repeated"})
                return False

            # --- DLN: Log the Proposed Plan ---
            self.session_manager.log_event("plan_proposed", {"plan": plan})

            # --- PLAN REVIEW & EDITING ---
            if self.require_confirmation:
                plan = self._review_and_edit_plan(plan)
                
                if plan is None:
                    print(f"{C.ERR}Plan rejected by human.{C.END}")
                    observation = "ERROR: Human operator rejected the plan. Ask what they want to change."
                    self.session_manager.log_event("human_intervention", {"action": "rejected"})
                    continue 

                if not plan:
                    print(f"{C.WARN}Plan is empty. Returning control to AI.{C.END}")
                    observation = "WARNING: The human cleared the plan. No actions were taken."
                    self.session_manager.log_event("human_intervention", {"action": "cleared_plan"})
                    continue

            # --- BATCH EXECUTION ---
            execution_success = True
            failed_step = None
            step_results = []
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
                    step_results.append({"step": step_idx + 1, "status": "FAILED", "error": "Device not connected"})
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
                        # --- DLN: Save Artifact directly to Experiment Folder ---
                        artifact_id = self.session_manager.save_data(current_entry_id, device, command, payload)
                        print(f"     {C.OK}[Notebook] Saved as artifact {artifact_id}{C.END}")
                        
                        collected_data.append({
                            "id": artifact_id,
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
            
            # --- DLN: Log result of the whole sequence ---
            self.session_manager.log_event("execution_result", {
                "success": execution_success,
                "steps": step_results,
                "error_detail": failed_step if not execution_success else None
            })
            
            if execution_success:
                print(f"{C.OK}[Agent] Plan executed successfully.{C.END}")
                self.last_failed_plan = None 
                
                if collected_data:
                    analysis_text = self._perform_aggregated_analysis(goal, collected_data)
                    # --- DLN: Log the Final Analysis ---
                    self.session_manager.log_event("one_shot_analysis", {"summary": analysis_text})
                
                return True 
            else:
                print(f"{C.ERR}[Agent] Plan aborted due to error.{C.END}")
                observation = f"EXECUTION FAILED: {failed_step}"
                self.last_failed_plan = plan

        return False

    def _perform_aggregated_analysis(self, user_goal, data_list):
        """
        Performs a One-Shot analysis on the COMPLETE set of data collected 
        during the plan execution.
        """
        print(f"\n{C.INFO}[Analysis] Aggregating results from {len(data_list)} datasets...{C.END}")
        
        relevant_devices = set(d['device'] for d in data_list)
        guidance_text = ""
        for dev in relevant_devices:
            text = self.planner.guidance_dict.get(dev, "")
            if text:
                guidance_text += f"[{dev.upper()} Guidance]: {text}\n"

        data_summary = ""
        for item in data_list:
            core_data = item['payload'].get('data', item['payload'])
            data_summary += f"\n--- DATASET {item['id']} ---\n"
            data_summary += f"Source: {item['device']}.{item['command']}({item['args']})\n"
            data_summary += f"Content: {json.dumps(core_data, indent=None)}\n"

        system_prompt = (
            "You are a Scientific Data Analyst. "
            "Interpret experimental results concierge-style. Identify trends and peaks. "
            "Be concise. Describe the science, not the JSON."
        )
        
        user_prompt = (
            f"User Goal: {user_goal}\n\n"
            f"Instrument Guidance:\n{guidance_text}\n"
            f"Collected Data:\n{data_summary}\n\n"
            "Analyze these results."
        )

        try:
            analyst = LLMManager.get_agent(context=system_prompt) 
            summary = analyst.prompt(user_prompt, use_history=False)
            
            print(f"\n{C.INFO}--- EXPERIMENT ANALYSIS ---{C.END}")
            print(f"{summary}")
            print(f"{C.INFO}---------------------------{C.END}\n")
            return summary
            
        except Exception as e:
            print(f"{C.ERR}     [Analysis Failed] {e}{C.END}")
            return f"Analysis failed: {e}"

    def _review_and_edit_plan(self, plan):
        while True:
            print(f"\n{C.WARN}--- PLAN REVIEW (CTRL-C to abort) ---{C.END}")
            if not plan:
                print(f"  {C.ERR}(Plan is empty){C.END}")
            else:
                for idx, step in enumerate(plan):
                    dev = step.get('device', 'unknown').upper()
                    cmd = step.get('command', 'unknown')
                    args = json.dumps(step.get('args', {}))
                    print(f"  {C.INFO}{idx+1}.{C.END} {dev}: {cmd} {args}")

            print(f"\n{C.INFO}Commands: 'run' (or y), 'reject' (or n), 'del <#>', 'edit <#>'{C.END}")
            try:
                user_input = input(f"Action > ").strip()
            except EOFError: return None
            
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
                new_args_raw = input("Enter new args (JSON) or 'c': ").strip()
                if new_args_raw.lower() == 'c': continue
                try:
                    new_args = json.loads(new_args_raw)
                    if isinstance(new_args, dict):
                        plan[idx]['args'] = new_args
                        print(f"{C.OK}Step updated.{C.END}")
                except json.JSONDecodeError:
                    print(f"{C.ERR}Invalid JSON string.{C.END}")

    def _update_executor_state(self, command, args):
        """Updates internal memory of well position and plate contents."""
        if command in ('to_well', 'dispense_at', 'to_well_and_dispense'):
            well = args.get('well')
            if well: self.last_known_well = well.upper()
        
        if command in ('dispense', 'dispense_at', 'to_well_and_dispense'):
            well = args.get('well') or args.get('to_well') or self.last_known_well
            pump = args.get('pump')
            vol = args.get('vol', 0)
            if well and pump and vol > 0:
                self.plate_manager.add_liquid(well, pump, vol)

    def _wait_for_result(self, port, timeout=60):
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