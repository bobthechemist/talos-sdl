# host/ai/test_agent_stage2.py
import sys
import time
import json
from pathlib import Path

# Setup project root path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(PROJECT_ROOT))

from host.core.device_manager import DeviceManager
from host.lab.sidekick_plate_manager import PlateManager
from host.ai.llm_manager import LLMManager
from host.ai.planner import Planner
from host.ai.agent_executor import AgentExecutor
from host.ai.ai_utils import connect_devices, check_devices_attached
from host.gui.console import C

def main():
    print(f"{C.INFO}=== Stage 2: Stateful ReAct Loop Test ==={C.END}")

    # 1. Setup World Model
    world_model = {
        "reagents": {
            "p1": "Red Reagent",
            "p2": "Ligand",
            "p3": "Buffer",
            "p4": "Water"
        },
        "plate_is_empty": True,
        "max_well_volume_ul": 250.0,
        "experiment_name": "Stage2_Test"
    }

    # 2. Initialize Components
    plate_manager = PlateManager(max_volume_ul=world_model['max_well_volume_ul'])
    planner = Planner(world_model=world_model, command_sets={}) # Will be updated after connect
    
    # 3. Connect to Hardware
    # We use the helper from ai_utils to find Sidekick and Colorimeter
    if not check_devices_attached():
        print(f"{C.ERR}Hardware not found. Please connect Sidekick and Colorimeter (or Fake devices).{C.END}")
        return

    manager, device_ports = connect_devices()
    if not manager:
        return

    from host.ai.ai_utils import get_instructions
    full_responses = get_instructions(manager, device_ports)
    if not full_responses:
        print(f"{C.ERR}Failed to get device capabilities.{C.END}")
        manager.stop(); return
    
    ai_commands = {}
    ai_guidance = {}
    
    for dev, payload in full_responses.items():
        # Extract the command dictionary
        cmd_data = payload.get('data', {})
        ai_commands[dev] = {k: v for k, v in cmd_data.items() if v.get('ai_enabled', False)}
        
        # Extract the metadata guidance
        metadata = payload.get('metadata', {})
        ai_guidance[dev] = metadata.get('ai_guidance', "No specific guidance provided.")

    # 5. Initialize the Planner with guidance
    planner = Planner(
        world_model=world_model, 
        command_sets=ai_commands, 
        guidance_dict=ai_guidance
    )

    # 6. Initialize the Agent with the system context
    agent = LLMManager.get_agent(
        provider="vertex", 
        context=planner.build_system_context()
    )

    # 7. Create and Run the Executor (Memory/PlateManager included)
    executor = AgentExecutor(manager, device_ports, agent, planner, plate_manager)
    
    goal = "Add 100uL of Red reagent to well A1. If and only if that succeeds, measure the spectrum of A1."

    try:
        executor.run(goal)
    except KeyboardInterrupt:
        print("\nTest aborted by user.")
    except Exception as e:
        print(f"\n{C.ERR}An error occurred during execution: {e}{C.END}")
    finally:
        executor.save_log()
        print(f"\n{C.INFO}Shutting down Device Manager...{C.END}")
        manager.stop()

if __name__ == "__main__":
    main()