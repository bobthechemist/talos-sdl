# host/ai/agent_executor.py
import time
import json
import os
import queue
from datetime import datetime
from host.gui.console import C
from shared_lib.messages import Message

class AgentExecutor:
    def __init__(self, manager, device_ports, agent, planner, plate_manager):
        self.manager = manager
        self.device_ports = device_ports
        self.agent = agent
        self.planner = planner
        self.plate_manager = plate_manager
        self.total_tokens = 0
        self.session_history = [] # For logging

    def run(self, goal, max_steps=10):
        print(f"\n{C.INFO}[Agent] Starting loop for goal: '{goal}'{C.END}")
        observation = None
        self.total_tokens = 0
        
        # Log the start of the session and the system context
        self.session_history = [{
            "timestamp": datetime.now().isoformat(),
            "event": "session_start",
            "goal": goal,
            "system_context": self.planner.build_system_context(),
            "world_model": self.planner.world_model
        }]
        
        for i in range(max_steps):
            plate_summary = self.plate_manager.get_plate_summary()
            prompt = self.planner.build_user_prompt(goal, plate_summary, observation)
            
            print(f"[*] Thinking... (Turn {i+1})")
            response = self.agent.prompt(prompt, use_history=True)
            
            if response is None:
                print(f"{C.ERR}[Agent] Critical: The AI provider failed.{C.END}")
                break

            usage = self.agent.last_run_info
            self.total_tokens += usage['total_tokens']
            print(f"    {C.INFO}[Tokens] Turn: {usage['total_tokens']} | Cumulative: {self.total_tokens}{C.END}")
            
            # turn_log captures the LLM interaction
            turn_log = {
                "turn": i + 1,
                "timestamp": datetime.now().isoformat(),
                "prompt_sent": prompt,
                "response_raw": response,
                "usage": usage
            }

            try:
                json_str = response
                if "```json" in response:
                    json_str = response.split("```json")[1].split("```")[0]
                elif "```" in response:
                    json_str = response.split("```")[1].split("```")[0]
                action = json.loads(json_str.strip())
                turn_log["action_parsed"] = action
            except Exception as e:
                print(f"{C.ERR}Failed to parse AI response as JSON: {e}{C.END}")
                turn_log["error"] = f"JSON Parse Error: {str(e)}"
                self.session_history.append(turn_log)
                break

            if action.get("status") == "COMPLETE":
                print(f"\n{C.OK}[Agent] Task Finished: {action.get('message')}{C.END}")
                turn_log["event"] = "task_complete"
                self.session_history.append(turn_log)
                break

            # Hardware execution
            device = action.get("device", "").lower()
            command = action.get("command")
            args = action.get("args", {})
            port = self.device_ports.get(device)

            if not port:
                observation = f"ERROR: Device '{device}' unknown."
                turn_log["hardware_interaction"] = {"error": observation}
                self.session_history.append(turn_log)
                continue

            print(f"{C.WARN}[Step {i+1}] {device.upper()} -> {command}({args}){C.END}")
            instruction_msg = Message.create_message("AGENT_EXECUTOR", "INSTRUCTION", payload={"func": command, "args": args})
            self.manager.send_message(port, instruction_msg) 
            
            result = self._wait_for_result(port)
            observation = f"Observation from {device}: {result['status']} - {result['payload']}"
            
            # Log the hardware result
            turn_log["hardware_interaction"] = {
                "device": device,
                "command": command,
                "args": args,
                "result_status": result['status'],
                "result_payload": result['payload']
            }

            if result['status'] == "PROBLEM":
                print(f"{C.ERR}    << {observation}{C.END}")
            else:
                print(f"{C.OK}    << {observation}{C.END}")

            # Memory update
            if result['status'] == "SUCCESS":
                if command in ('dispense', 'dispense_at', 'to_well'):
                    well = args.get('well') or args.get('to_well')
                    pump = args.get('pump')
                    vol = args.get('vol', 0)
                    if well and pump and vol > 0:
                        self.plate_manager.add_liquid(well, pump, vol)
                        turn_log["memory_update"] = f"Added {vol}uL to {well} via {pump}"

            self.session_history.append(turn_log)

    def _wait_for_result(self, port, timeout=60):
        # ... (Method remains unchanged)
        start = time.time()
        while time.time() - start < timeout:
            try:
                msg_type, msg_port, msg_data = self.manager.incoming_message_queue.get(timeout=1)
                if msg_port == port and msg_type == 'RECV':
                    if msg_data.status in ("SUCCESS", "PROBLEM", "DATA_RESPONSE"):
                        return {"status": msg_data.status, "payload": msg_data.payload}
            except queue.Empty:
                continue
        return {"status": "ERROR", "payload": "Hardware timeout."}

    def save_log(self):
        """Saves the session history to a timestamped JSON file in the temp/ directory."""
        if not os.path.exists("temp"):
            os.makedirs("temp")
            
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"temp/one-goal-{timestamp}.json"
        
        try:
            with open(filename, 'w') as f:
                json.dump(self.session_history, f, indent=2)
            print(f"\n{C.INFO}[Log] Session record saved to: {filename}{C.END}")
        except Exception as e:
            print(f"{C.ERR}Failed to save log file: {e}{C.END}")