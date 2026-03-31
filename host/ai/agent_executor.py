# host/ai/agent_executor.py
import time
import json
import queue
import re
from host.gui.console import C
from shared_lib.messages import Message
from host.ai.llm_manager import LLMManager

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
        # Persistence across steps in a single run
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
        
        # 1. Log INTENT
        intent_id = self.session_manager.log_intent(goal)
        
        for i in range(max_turns):
            # Reset sticky tags for this specific attempt at the goal
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
            if plan == self.last_failed_plan:
                return False

            # 2. PLAN REVIEW
            if self.require_confirmation:
                plan = self._review_and_edit_plan(plan)
                if plan is None:
                    observation = "ERROR: Human operator rejected the plan."
                    continue 

            self.session_manager.log_plan(plan)

            # 3. EXECUTION
            execution_success = True
            collected_data = [] 
            
            print(f"\n{C.INFO}Executing Plan...{C.END}")
            for step_idx, step in enumerate(plan):
                device = step.get("device", "").lower()
                command = step.get("command")
                args = step.get("args", {})
                
                # UPDATE STICKY TAGS: 
                # If this step mentions a 'well' or 'vial', remember it for subsequent steps
                self.active_run_tags.update(self._extract_context_tags(args))
                
                print(f"  -> Step {step_idx+1}/{len(plan)}: {device} {command}...", end="", flush=True)

                port = self.device_ports.get(device)
                if not port:
                    print(f" {C.ERR}[FAILED]{C.END}")
                    execution_success = False; break

                self.manager.send_message(port, Message.create_message("AGENT", "INSTRUCTION", payload={"func": command, "args": args})) 
                result = self._wait_for_result(port)

                if result['status'] in ("SUCCESS", "DATA_RESPONSE"):
                    print(f" {C.OK}[OK]{C.END}")
                    
                    if result['status'] == "DATA_RESPONSE":
                        # MERGE current sticky tags with the observation
                        artifact_id = self.session_manager.save_observation(
                            intent_id, device, command, result['payload'], tags=self.active_run_tags.copy()
                        )
                        print(f"     {C.OK}[Notebook] Saved Observation with tags: {self.active_run_tags}{C.END}")
                        
                        collected_data.append({
                            "id": artifact_id, "device": device, "command": command, 
                            "args": args, "payload": result['payload'], 
                            "context": self.active_run_tags.copy() # Pass context to analyzer
                        })

                    self._update_executor_state(command, args)
                else:
                    print(f" {C.ERR}[PROBLEM]{C.END}")
                    execution_success = False; break
            
            if execution_success:
                if collected_data:
                    # 4. REFLECTION
                    analysis_text = self._perform_aggregated_analysis(goal, collected_data)
                    self.session_manager.log_reflection(analysis_text)
                return True 
            else:
                observation = f"EXECUTION FAILED at step {step_idx+1}"
                self.last_failed_plan = plan

        return False

    def _perform_aggregated_analysis(self, user_goal, data_list):
        """Includes context tags in the analysis prompt so the AI can interpret 'G9' correctly."""
        print(f"\n{C.INFO}[Analysis] Summarizing findings...{C.END}")
        
        data_summary = ""
        for item in data_list:
            core_data = item['payload'].get('data', item['payload'])
            # We explicitly tell the analyzer what the context (G9) was
            context_str = f" Context: {item['context']}" if item['context'] else ""
            data_summary += f"Dataset {item['id']} (from {item['device']}.{item['command']}){context_str}: {json.dumps(core_data)}\n"

        system_prompt = "You are a Scientific Data Analyst. Interpret results in context of the experimental setup."
        user_prompt = f"Goal: {user_goal}\nData:\n{data_summary}\nAnalyze these results."

        analyst = LLMManager.get_agent(context=system_prompt) 
        return analyst.prompt(user_prompt, use_history=False)


    def _parse_ai_response(self, response):
        try:
            json_str = response
            if "```json" in response: json_str = response.split("```json")[1].split("```")[0]
            elif "```" in response: json_str = response.split("```")[1].split("```")[0]
            return json.loads(json_str.strip())
        except Exception as e:
            print(f"{C.WARN}[Agent] Message: {response.strip()}{C.END}")
            return None

    def _perform_aggregated_analysis(self, user_goal, data_list):
        """Generates a scientific summary and records it as a Reflection."""
        print(f"\n{C.INFO}[Analysis] Summarizing findings...{C.END}")
        
        data_summary = ""
        for item in data_list:
            core_data = item['payload'].get('data', item['payload'])
            data_summary += f"Dataset {item['id']} (from {item['device']}.{item['command']}): {json.dumps(core_data)}\n"

        system_prompt = "You are a Scientific Data Analyst. Describe results concisely in terms of chemistry/physics."
        user_prompt = f"Goal: {user_goal}\nData:\n{data_summary}\nAnalyze these results."

        analyst = LLMManager.get_agent(context=system_prompt) 
        summary = analyst.prompt(user_prompt, use_history=False)
        
        print(f"\n{C.INFO}--- EXPERIMENT ANALYSIS ---{C.END}")
        print(f"{summary}")
        print(f"{C.INFO}---------------------------{C.END}\n")
        return summary

    def _update_executor_state(self, command, args):
        # Keeps the local PlateManager synced for volume safety
        if command in ('to_well', 'dispense_at', 'to_well_and_dispense'):
            well = args.get('well')
            if well: self.plate_manager.last_known_well = well.upper()
        if command in ('dispense', 'dispense_at', 'to_well_and_dispense'):
            well = args.get('well') or getattr(self.plate_manager, 'last_known_well', None)
            pump, vol = args.get('pump'), args.get('vol', 0)
            if well and pump and vol > 0: self.plate_manager.add_liquid(well, pump, vol)

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

    def _review_and_edit_plan(self, plan):
        # (Existing review logic remains compatible)
        print(f"\n{C.WARN}--- PLAN REVIEW ---{C.END}")
        for idx, step in enumerate(plan):
            print(f"  {idx+1}. {step.get('device')}: {step.get('command')} {step.get('args')}")
        user_input = input(f"\nRun? (y/n) > ").strip().lower()
        return plan if user_input in ('y', 'yes', 'run') else None