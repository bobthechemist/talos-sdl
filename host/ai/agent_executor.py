# host/ai/agent_executor.py
import time
import json
import queue
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

    def run(self, goal, max_steps=10):
        print(f"\n{C.INFO}[Agent] Starting loop for goal: '{goal}'{C.END}")
        observation = None
        self.total_tokens = 0
        
        for i in range(max_steps):
            plate_summary = self.plate_manager.get_plate_summary()
            prompt = self.planner.build_user_prompt(goal, plate_summary, observation)
            
            print(f"[*] Thinking... (Turn {i+1})")
            response = self.agent.prompt(prompt, use_history=True)
            
            # 1. Check for Agent failure
            if response is None:
                print(f"{C.ERR}[Agent] Critical: The AI provider failed to return a response.{C.END}")
                break

            # 2. Display Tokens
            usage = self.agent.last_run_info
            self.total_tokens += usage['total_tokens']
            print(f"    {C.INFO}[Tokens] Turn: {usage['total_tokens']} | Cumulative: {self.total_tokens}{C.END}")
            
            # 3. Parse JSON
            try:
                json_str = response
                if "```json" in response:
                    json_str = response.split("```json")[1].split("```")[0]
                elif "```" in response:
                    json_str = response.split("```")[1].split("```")[0]
                
                action = json.loads(json_str.strip())
            except Exception as e:
                print(f"{C.ERR}Failed to parse AI response as JSON: {e}{C.END}")
                print(f"Raw response: {response}")
                break

            # 4. Check for Completion
            if action.get("status") == "COMPLETE":
                print(f"\n{C.OK}[Agent] Task Finished: {action.get('message')}{C.END}")
                break

            # 5. Execute Hardware Action
            device = action.get("device", "").lower()
            command = action.get("command")
            args = action.get("args", {})
            port = self.device_ports.get(device)

            if not port:
                observation = f"ERROR: Device '{device}' not connected."
                print(f"{C.ERR}    {observation}{C.END}")
                continue

            print(f"{C.WARN}[Step {i+1}] {device.upper()} -> {command}({args}){C.END}")
            
            instruction_msg = Message.create_message(
                subsystem_name="AGENT_EXECUTOR", 
                status="INSTRUCTION", 
                payload={"func": command, "args": args}
            )
            self.manager.send_message(port, instruction_msg) 
            
            # 6. Wait for Hardware Result
            result = self._wait_for_result(port)
            observation = f"Observation from {device}: {result['status']} - {result['payload']}"
            
            if result['status'] == "PROBLEM":
                print(f"{C.ERR}    << {observation}{C.END}")
            else:
                print(f"{C.OK}    << {observation}{C.END}")

            # 7. Update Memory
            if result['status'] == "SUCCESS":
                if command in ('dispense', 'dispense_at', 'to_well'):
                    well = args.get('well') or args.get('to_well')
                    pump = args.get('pump')
                    vol = args.get('vol', 0)
                    if well and pump and vol > 0:
                        self.plate_manager.add_liquid(well, pump, vol)
                        print(f"{C.INFO}    [Memory] Well {well} updated.{C.END}")

    def _wait_for_result(self, port, timeout=60):
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