# host/ai/agent_executor.py
import time
import json
import queue
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
        self.session_manager = session_manager 
        self.total_tokens = 0
        self.require_confirmation = require_confirmation
        self.last_failed_plan = None 
        self.active_run_tags = {}

    def _extract_context_tags(self, args):
        tags = {}
        id_keys = ['well', 'vial', 'sample', 'id', 'location', 'channel', 'electrode', 'pump']
        if isinstance(args, dict):
            for k, v in args.items():
                if k.lower() in id_keys:
                    tags[k.lower()] = str(v)
        return tags

    def run(self, goal, max_turns=3):
        observation = None
        self.last_failed_plan = None
        intent_id = self.session_manager.log_intent(goal)
        
        for i in range(max_turns):
            self.active_run_tags = {} 
            plate_summary = self.plate_manager.get_plate_summary()
            prompt = self.planner.build_user_prompt(goal, plate_summary, observation=observation)

            print(f"[*] Thinking... (Turn {i+1}/{max_turns})")
            response = self.agent.prompt(prompt, use_history=True)
            if not response: break

            ai_data = self._parse_ai_response(response)
            if not ai_data: return True

            if ai_data.get("status") == "COMPLETE":
                print(f"\n{C.OK}[Agent] {ai_data.get('message')}{C.END}")
                self.session_manager.log_reflection(ai_data.get('message'))
                return True

            plan = ai_data.get("plan", [])
            
            # --- RESTORED PLAN REVIEW GATE ---
            if self.require_confirmation:
                plan = self._review_and_edit_plan(plan)
                if plan is None:
                    print(f"{C.ERR}Plan rejected by human.{C.END}")
                    observation = "ERROR: Human operator rejected the plan."
                    continue 

            # Log the FINAL approved plan to the Ledger for audit purposes
            self.session_manager.log_plan(plan)

            # --- EXECUTION ---
            execution_success = True
            collected_data = [] 
            print(f"\n{C.INFO}Executing Plan...{C.END}")
            
            for step_idx, step in enumerate(plan):
                device = step.get("device", "").lower()
                command = step.get("command")
                args = step.get("args", {})
                
                self.active_run_tags.update(self._extract_context_tags(args))
                print(f"  -> Step {step_idx+1}/{len(plan)}: {device} {command}...", end="", flush=True)

                port = self.device_ports.get(device)
                if not port:
                    print(f" {C.ERR}[FAILED]{C.END} (Device not found)")
                    execution_success = False; break

                self.manager.send_message(port, Message.create_message("AGENT", "INSTRUCTION", payload={"func": command, "args": args})) 
                result = self._wait_for_result(port)

                if result['status'] in ("SUCCESS", "DATA_RESPONSE"):
                    print(f" {C.OK}[OK]{C.END}")
                    if result['status'] == "DATA_RESPONSE":
                        artifact_id = self.session_manager.save_observation(
                            intent_id, device, command, result['payload'], tags=self.active_run_tags.copy()
                        )
                        print(f"     {C.OK}[Notebook] Saved Observation with tags: {self.active_run_tags}{C.END}")
                        collected_data.append({
                            "id": artifact_id, "device": device, "command": command, 
                            "args": args, "payload": result['payload'], "context": self.active_run_tags.copy()
                        })
                    self._update_executor_state(command, args)
                else:
                    print(f" {C.ERR}[PROBLEM]{C.END}")
                    execution_success = False; break
            
            if execution_success:
                if collected_data:
                    analysis_text = self._perform_aggregated_analysis(goal, collected_data)
                    self.session_manager.log_reflection(analysis_text)
                return True 
            else:
                observation = f"EXECUTION FAILED at step {step_idx+1}"
                self.last_failed_plan = plan
        return False

    def _review_and_edit_plan(self, plan):
        """
        FULL HITL INTERFACE: Restore edit, delete, and run commands.
        """
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

            print(f"\n{C.INFO}Commands: 'run' (or y), 'reject' (or n), 'del <#>', 'edit <#>', 'add'{C.END}")
            try:
                user_input = input(f"Action > ").strip().lower()
            except EOFError: return None
            
            if user_input in ('run', 'y', 'yes'):
                return plan
            if user_input in ('reject', 'no', 'n'):
                return None
            
            parts = user_input.split()
            if not parts: continue
            
            cmd = parts[0]
            
            # Delete Logic
            if cmd == 'del' and len(parts) > 1:
                try:
                    idx = int(parts[1]) - 1
                    removed = plan.pop(idx)
                    print(f"{C.WARN}Removed step {idx+1}: {removed['command']}{C.END}")
                    continue
                except (ValueError, IndexError):
                    print(f"{C.ERR}Invalid index.{C.END}")

            # Edit Logic
            elif cmd == 'edit' and len(parts) > 1:
                try:
                    idx = int(parts[1]) - 1
                    step = plan[idx]
                    print(f"{C.INFO}Editing Step {idx+1}:{C.END} {step['device']} -> {step['command']}")
                    print(f"Current Args: {json.dumps(step.get('args', {}))}")
                    new_args_raw = input("Enter new args (JSON) or 'c' to cancel: ").strip()
                    if new_args_raw.lower() == 'c': continue
                    new_args = json.loads(new_args_raw)
                    if isinstance(new_args, dict):
                        plan[idx]['args'] = new_args
                        print(f"{C.OK}Step updated.{C.END}")
                except (ValueError, IndexError, json.JSONDecodeError):
                    print(f"{C.ERR}Invalid index or JSON format.{C.END}")

            # Add Logic (Manual Step Injection)
            elif cmd == 'add':
                try:
                    print(f"{C.INFO}Add Manual Step{C.END}")
                    dev = input("Device: ").strip().lower()
                    func = input("Command: ").strip().lower()
                    args_raw = input("Args (JSON): ").strip()
                    args = json.loads(args_raw) if args_raw else {}
                    plan.append({"device": dev, "command": func, "args": args})
                    print(f"{C.OK}Step added.{C.END}")
                except Exception as e:
                    print(f"{C.ERR}Failed to add step: {e}{C.END}")

            else:
                print(f"{C.ERR}Unknown command. Use run, reject, del #, or edit #.{C.END}")

    def _parse_ai_response(self, response):
        try:
            json_str = response
            if "```json" in response: json_str = response.split("```json")[1].split("```")[0]
            elif "```" in response: json_str = response.split("```")[1].split("```")[0]
            return json.loads(json_str.strip())
        except Exception: return None

    def _wait_for_result(self, port, timeout=60):
        start = time.time()
        while time.time() - start < timeout:
            try:
                msg_type, msg_port, msg_data = self.manager.incoming_message_queue.get(timeout=1)
                if msg_port == port and msg_type == 'RECV':
                    if msg_data.status in ("SUCCESS", "PROBLEM", "DATA_RESPONSE"):
                        return {"status": msg_data.status, "payload": msg_data.payload}
            except queue.Empty: continue
        return {"status": "ERROR", "payload": "Hardware timeout."}

    def _perform_aggregated_analysis(self, user_goal, data_list):
        data_summary = ""
        for item in data_list:
            core_data = item['payload'].get('data', item['payload'])
            context_str = f" Context: {item['context']}" if item['context'] else ""
            data_summary += f"Dataset {item['id']} ({item['device']}){context_str}: {json.dumps(core_data)}\n"

        system_prompt = "You are a Scientific Data Analyst. Interpret results concisely."
        user_prompt = f"Goal: {user_goal}\nData:\n{data_summary}\nAnalyze these results."
        analyst = LLMManager.get_agent(context=system_prompt) 
        return analyst.prompt(user_prompt, use_history=False)

    def _update_executor_state(self, command, args):
        if command in ('to_well', 'dispense_at', 'to_well_and_dispense'):
            well = args.get('well')
            if well: self.plate_manager.last_known_well = well.upper()
        if command in ('dispense', 'dispense_at', 'to_well_and_dispense'):
            well = args.get('well') or getattr(self.plate_manager, 'last_known_well', None)
            pump, vol = args.get('pump'), args.get('vol', 0)
            if well and pump and vol > 0: self.plate_manager.add_liquid(well, pump, vol)