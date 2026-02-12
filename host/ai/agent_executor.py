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

    def run(self, goal, max_steps=10):
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
        
        for i in range(max_steps):
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
                turn_log["error"] = str(e)
                self.session_history.append(turn_log)
                break

            if action.get("status") == "COMPLETE":
                print(f"\n{C.OK}[Agent] {action.get('message')}{C.END}")
                turn_log["event"] = "task_complete"
                self.session_history.append(turn_log)
                return True

            device = action.get("device", "").lower()
            command = action.get("command")
            args = action.get("args", {})
            port = self.device_ports.get(device)

            if not port:
                observation = f"ERROR: Device '{device}' not connected or unknown."
                print(f"{C.ERR}    {observation}{C.END}")
                turn_log["hardware_interaction"] = {"error": observation}
                self.session_history.append(turn_log)
                continue

            # --- Safety Gate ---
            print(f"\n{C.WARN}PROPOSED ACTION:{C.END}")
            print(f"  Device:  {device.upper()}")
            print(f"  Command: {command}")
            print(f"  Args:    {args}")
            
            if self.require_confirmation:
                confirm = input(f"{C.INFO}Execute this command? [Y/n]: {C.END}").strip().lower()
                if confirm not in ('', 'y', 'yes'):
                    print(f"{C.ERR}Action aborted by human.{C.END}")
                    observation = "ERROR: Human operator rejected this command."
                    turn_log["hardware_interaction"] = {"status": "REJECTED_BY_HUMAN"}
                    self.session_history.append(turn_log)
                    continue

            # Execute Hardware Command
            instruction_msg = Message.create_message(
                subsystem_name="AGENT_EXECUTOR", 
                status="INSTRUCTION", 
                payload={"func": command, "args": args}
            )
            self.manager.send_message(port, instruction_msg) 
            
            # Polling for hardware response
            result = self._wait_for_result(port)
            observation = f"Observation from {device}: {result['status']} - {result['payload']}"
            
            turn_log["hardware_interaction"] = {
                "device": device, "command": command, "args": args,
                "result_status": result['status'], "result_payload": result['payload']
            }

            if result['status'] == "PROBLEM":
                print(f"{C.ERR}    << {observation}{C.END}")
            else:
                print(f"{C.OK}    << {observation}{C.END}")

            # Update Memory on Success
            if result['status'] == "SUCCESS":
                if command in ('dispense', 'dispense_at', 'to_well'):
                    well = args.get('well') or args.get('to_well')
                    pump = args.get('pump')
                    vol = args.get('vol', 0)
                    if well and pump and vol > 0:
                        self.plate_manager.add_liquid(well, pump, vol)
                        print(f"{C.INFO}    [Memory] Updated PlateManager: {well}{C.END}")

            self.session_history.append(turn_log)
        
        return False

    def _wait_for_result(self, port, timeout=60):
        """Polls the DeviceManager queue for a response from the specific port."""
        start = time.time()
        while time.time() - start < timeout:
            try:
                # Polling for (msg_type, port, msg_data)
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