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

    # 4. Get Command Sets (Help) from devices to populate Planner
    from host.ai.ai_utils import get_instructions
    print(f"[*] Fetching device capabilities...")
    raw_commands = get_instructions(manager, device_ports)
    if not raw_commands:
        print(f"{C.ERR}Failed to get device commands.{C.END}")
        manager.stop()
        return
    
    # Filter for AI enabled commands (simulating what ai-plan.py does)
    ai_commands = {}
    for dev, cmds in raw_commands.items():
        ai_commands[dev] = {k: v for k, v in cmds.items() if v.get('ai_enabled', False)}
    
    planner.command_sets = ai_commands

    # 5. Initialize the Agent
    agent = LLMManager.get_agent(
        provider="vertex", 
        context=planner.build_system_context()
    )

    # 6. Create and Run the Executor
    executor = AgentExecutor(
        manager=manager,
        device_ports=device_ports,
        agent=agent,
        planner=planner,
        plate_manager=plate_manager
    )

    # TEST SCENARIO
    goal = "Add 100uL of Red reagent to well A1. If and only if that succeeds, measure the spectrum of A1."
    
    try:
        executor.run(goal)
    except KeyboardInterrupt:
        print("\nTest aborted by user.")
    except Exception as e:
        print(f"\n{C.ERR}An error occurred during execution: {e}{C.END}")
    finally:
        print(f"\n{C.INFO}Shutting down Device Manager...{C.END}")
        manager.stop()

if __name__ == "__main__":
    main()