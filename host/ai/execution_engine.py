# host/ai/execution_engine.py
import time
import queue
import json
from host.gui.console import C
from shared_lib.messages import Message

class ExecutionEngine:
    """
    A streamlined engine responsible ONLY for executing a pre-approved plan.
    It has no planning or AI capabilities.
    """
    def __init__(self, manager, device_ports, dln, host_tools=None, app=None):
        self.manager = manager
        self.device_ports = device_ports
        self.dln = dln
        self.host_tools = host_tools if host_tools is not None else {}
        self.app = app
        self.current_plan = []
        self.current_step_idx = 0

    def inject_steps(self, new_steps: list, immediate: bool = True) -> None:
        """Appends or inserts new steps into the active execution plan at runtime."""
        if immediate:
            # Insert right after the currently executing step
            insert_pos = self.current_step_idx + 1
            self.current_plan = self.current_plan[:insert_pos] + new_steps + self.current_plan[insert_pos:]
        else:
            self.current_plan.extend(new_steps)

    def execute_plan(self, plan: list, plan_id: int = None):
        """Executes a list of command steps sequentially with support for dynamic evaluation."""
        # --- RE-ENTRANCY SAFEGUARD ---
        # Save previous state in case this was called recursively by a host tool (like submit_intent)
        prev_plan = self.current_plan
        prev_idx = self.current_step_idx

        print(f"\n{C.INFO}Executing Plan (ID: {plan_id})...{C.END}")
        self.current_plan = plan
        self.current_step_idx = 0

        while self.current_step_idx < len(self.current_plan):
            step = self.current_plan[self.current_step_idx]
            device = step.get("device", "").lower()
            command = step.get("command")
            args = step.get("args", {})
            
            print(f"  -> Step {self.current_step_idx + 1}/{len(self.current_plan)}: {device}.{command}()...", end="", flush=True)

            if device == "host":
                if command in self.host_tools:
                    try:
                        # Invoke the host callback passing `self.app` instead of `self.dln`
                        result = self.host_tools[command](args, plan_id, self.current_step_idx, self, self.app)
                        print(f" {C.OK}[OK]{C.END}")
                        
                        # Pythonic routing: If it returns a dict, log it as a DATA_RESPONSE
                        if isinstance(result, dict):
                            self._handle_data_response(device, command, args, result, plan_id, self.current_step_idx)
                            
                    except Exception as e:
                        error_msg = f"Host tool '{command}' failed: {str(e)}"
                        self.dln.log_science(entry_type="system", data={"message": "Plan did not complete successfully.", "plan_id": plan_id, "step_index": self.current_step_idx, "error": error_msg})
                        print(f" {C.ERR}[PROBLEM]{C.END}\n     {C.WARN}-> Error: {error_msg}{C.END}")
                        break
                else:
                    error_msg = f"Host command '{command}' is not registered in host_tools."
                    self.dln.log_science(entry_type="system", data={"message": "Plan did not complete successfully.", "plan_id": plan_id, "step_index": self.current_step_idx, "error": error_msg})
                    print(f" {C.ERR}[FAILED]{C.END}\n     {C.WARN}-> Error: {error_msg}{C.END}")
                    break
            else:
                port = self.device_ports.get(device)
                if not port:
                    error_msg = f"Device '{device}' not found in connected ports."
                    self.dln.log_science(entry_type="system", data={"message": "Plan did not complete successfully.", "plan_id": plan_id, "step_index": self.current_step_idx, "error": error_msg})
                    print(f" {C.ERR}[FAILED]{C.END}\n     {C.WARN}-> Error: {error_msg}{C.END}")
                    break

                msg = Message.create_message("HOST_ENGINE", "INSTRUCTION", payload={"func": command, "args": args})
                self.dln.log_transaction(f"SENT: {msg.serialize()}")
                self.manager.send_message(port, msg)
                
                result = self._wait_for_result(port)
                self.dln.log_transaction(f"RECV: {json.dumps(result)}")

                if result['status'] in ("SUCCESS", "DATA_RESPONSE"):
                    print(f" {C.OK}[OK]{C.END}")
                    if result['status'] == "DATA_RESPONSE":
                        self._handle_data_response(device, command, args, result['payload'], plan_id, self.current_step_idx)
                else:
                    error_msg = result.get('payload', 'Unknown hardware or serial error.')
                    self.dln.log_science(entry_type="system", data={"message": "Plan did not complete successfully.", "plan_id": plan_id, "step_index": self.current_step_idx, "error": error_msg})
                    print(f" {C.ERR}[PROBLEM]{C.END}\n     {C.WARN}-> Error: {error_msg}{C.END}")
                    break 

            self.current_step_idx += 1
        else:
            self.dln.log_science(entry_type="system", data={"message": "Plan executed successfully.", "plan_id": plan_id})
            print(f"{C.OK}Plan finished successfully.{C.END}")

        # --- RESTORE STATE ---
        self.current_plan = prev_plan
        self.current_step_idx = prev_idx

    def _wait_for_result(self, port, timeout=60):
        """Waits for a terminal response (SUCCESS, PROBLEM, DATA_RESPONSE) for a command."""
        start = time.time()
        while time.time() - start < timeout:
            try:
                msg_type, msg_port, msg_data = self.manager.incoming_message_queue.get(timeout=1)
                if msg_port == port and msg_type == 'RECV':
                    if msg_data.status in ("SUCCESS", "PROBLEM", "DATA_RESPONSE"):
                        return {"status": msg_data.status, "payload": msg_data.payload}
            except queue.Empty:
                continue
        return {"status": "ERROR", "payload": "Device timeout."}

    def _handle_data_response(self, device, command, args, payload, plan_id, step_idx):
        """Logs instrument data with plan linkage."""
        is_blob = len(json.dumps(payload)) > 4096 
        
        if is_blob:
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            filename = f"{device}_{command}_{timestamp}.json"
            blob_path = self.dln.store_blob(json.dumps(payload, indent=2).encode('utf-8'), filename)
            log_data = {
                "type": "blob_reference",
                "path": blob_path,
                "plan_metadata": {"plan_id": plan_id, "step_index": step_idx}
            }
        else:
            log_data = {
                "device": device,
                "command": command,
                "args": args,
                "payload": payload,
                "plan_metadata": {"plan_id": plan_id, "step_index": step_idx}
            }
        
        obs_id = self.dln.log_science(entry_type="observation", data=log_data)
        print(f" {C.OK}[Notebook] Logged Observation (ID: {obs_id}, PlanID: {plan_id}){C.END}")

        data_content = payload.get("data", payload)
        
        if is_blob:
            print(f"  {C.INFO}[DATA]: (Large Blob Saved to {blob_path}){C.END}")
        else:
            print(f"  {C.INFO}[DATA]: {data_content}{C.END}")

    def _extract_context_tags(self, args: dict) -> dict:
        """Finds common identifiers in args to tag data for easier relational queries."""
        tags = {}
        tag_keys = ['well', 'vial', 'sample', 'id', 'location']
        if isinstance(args, dict):
            for key, value in args.items():
                if key.lower() in tag_keys:
                    tags[key.lower()] = str(value)
        return tags