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
    def __init__(self, manager, device_ports, dln):
        self.manager = manager
        self.device_ports = device_ports
        self.dln = dln

    def execute_plan(self, plan: list, plan_id: int = None):
        """Executes a list of command steps sequentially, linked to a plan_id."""
        print(f"\n{C.INFO}Executing Plan (ID: {plan_id})...{C.END}")
        for step_idx, step in enumerate(plan):
            device = step.get("device", "").lower()
            command = step.get("command")
            args = step.get("args", {})
            
            print(f"  -> Step {step_idx+1}/{len(plan)}: {device}.{command}()...", end="", flush=True)

            port = self.device_ports.get(device)
            if not port:
                print(f" {C.ERR}[FAILED]{C.END}")
                break

            msg = Message.create_message("HOST_ENGINE", "INSTRUCTION", payload={"func": command, "args": args})
            self.dln.log_transaction(f"SENT: {msg.serialize()}")
            self.manager.send_message(port, msg)
            
            result = self._wait_for_result(port)
            self.dln.log_transaction(f"RECV: {json.dumps(result)}")

            if result['status'] in ("SUCCESS", "DATA_RESPONSE"):
                print(f" {C.OK}[OK]{C.END}")
                if result['status'] == "DATA_RESPONSE":
                    # Pass the plan_id and current step_idx
                    self._handle_data_response(device, command, args, result['payload'], plan_id, step_idx)
            else:
                print(f" {C.ERR}[PROBLEM]{C.END}")
                break 
        else:
            print(f"{C.OK}Plan finished successfully.{C.END}")

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

    def _extract_context_tags(self, args: dict) -> dict:
        """Finds common identifiers in args to tag data for easier relational queries."""
        tags = {}
        tag_keys = ['well', 'vial', 'sample', 'id', 'location']
        if isinstance(args, dict):
            for key, value in args.items():
                if key.lower() in tag_keys:
                    tags[key.lower()] = str(value)
        return tags