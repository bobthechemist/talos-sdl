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

    def execute_plan(self, plan: list):
        """
        Executes a list of command steps sequentially.

        Args:
            plan (list): A list of command dictionaries, each with 'device',
                         'command', and 'args'.
        """
        print(f"\n{C.INFO}Executing Plan...{C.END}")
        for step_idx, step in enumerate(plan):
            device = step.get("device", "").lower()
            command = step.get("command")
            args = step.get("args", {})
            
            print(f"  -> Step {step_idx+1}/{len(plan)}: {device}.{command}()...", end="", flush=True)

            port = self.device_ports.get(device)
            if not port:
                print(f" {C.ERR}[FAILED]{C.END} (Device '{device}' not found or connected)")
                break

            # Send the command and log the transaction
            msg = Message.create_message("HOST_ENGINE", "INSTRUCTION", payload={"func": command, "args": args})
            self.dln.log_transaction(f"SENT: {msg.serialize()}")
            self.manager.send_message(port, msg)
            
            # Wait for the result
            result = self._wait_for_result(port)
            self.dln.log_transaction(f"RECV: {json.dumps(result)}")

            if result['status'] in ("SUCCESS", "DATA_RESPONSE"):
                print(f" {C.OK}[OK]{C.END}")
                if result['status'] == "DATA_RESPONSE":
                    self._handle_data_response(device, command, args, result['payload'])
            else:
                print(f" {C.ERR}[PROBLEM]{C.END}\n     {result.get('payload')}")
                break # Stop execution on failure
        else: # This 'else' belongs to the 'for' loop, executes if the loop completed without break
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

    def _handle_data_response(self, device, command, args, payload):
        """Logs instrument data to the DLN."""
        # Simple check for large data (could be more sophisticated)
        is_blob = len(json.dumps(payload)) > 4096 # e.g., > 4KB is a blob
        
        if is_blob:
            # Handle as a blob
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            filename = f"{device}_{command}_{timestamp}.json"
            blob_path = self.dln.store_blob(json.dumps(payload, indent=2).encode('utf-8'), filename)
            log_data = {
                "type": "blob_reference",
                "content_type": "application/json",
                "path": blob_path,
                "description": f"Large data response from {device}.{command}"
            }
        else:
            # Handle as atomic data
            log_data = {
                "device": device,
                "command": command,
                "args": args,
                "payload": payload,
                "context_tags": self._extract_context_tags(args)
            }
        
        obs_id = self.dln.log_science(entry_type="observation", data=log_data)
        print(f" {C.OK}[Notebook] Logged Observation (ID: {obs_id}){C.END}")

    def _extract_context_tags(self, args: dict) -> dict:
        """Finds common identifiers in args to tag data for easier relational queries."""
        tags = {}
        tag_keys = ['well', 'vial', 'sample', 'id', 'location']
        if isinstance(args, dict):
            for key, value in args.items():
                if key.lower() in tag_keys:
                    tags[key.lower()] = str(value)
        return tags