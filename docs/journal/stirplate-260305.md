# testing agentic firmware design

Started the day with the intention to rework the stirplate. Decided to use the 4-motor featherwing controller with the idea that this would develop into a multi stir plate manager at some point but can right now quickly handle a single stir plate.

I fed the codebase to gemini and discussed the agentic design. We worked through the current socratic process, resulting in socratic_stirplate_manager. The process ran smoothly and AI generated the three files needed. Some additional modification was needed once the project was complete (integrating kickback) to make a functional stir plate out of DC computer fans. 

A new socratic_howto provides the flow needed to complete the agentic instrument design process.

# Talos lite

I need a simple lightweight way to interact with talos instruments. A short script (talos_lite) does not rely on anything in the Talos-SDL framework to communicate with an instrument. It has a very rudimentary connect/call/response interface which will be suitable for integrating tools like the stir plate into other projects.

# Lab-wide orchestration

I'm considering how to integrate non-CircuitPython tools into the Talos-SDL framework. This shift will require modifying the physical transport (currently USB Serial/VID:PID), adding options for virtual devices, and modifying the postman class. Tool discovery will need to be rethought. 

I had gemini create a prompt for this next activity, which is an important step before moving towards MCP

***

### The Task Prompt

"You have access to the entire codebase for Talos-SDL, a self-driving laboratory framework for developing agentic scientific instruments. Familiarize yourself with the project and then I will provide you with today's task."

**[PASTE ALL-IN-ONE CODEBASE HERE]**

**Today’s Task: Implementing the 'Ghost Machine' Architecture (v1.5)**

The goal is to evolve the framework so it can control instruments that are NOT running the standard Talos CircuitPython firmware. We need to implement 'Ghost Machines'—Host-side drivers that reside in the `host/` world but look and act like standard `Device` models to the AI Agent. We will use the **IO Rodeo Potentiostat** (a non-CircuitPython, serial-based device) as our primary case study.

Please execute this task in the following four milestones. **Stop after each milestone and provide a summary of the changes for my review before proceeding.**

---

### Milestone 1: Transport & Device Abstraction
Currently, `host/core/device.py` is hard-coded to instantiate a `SerialPostman`. We need to decouple the **Logical Device** (the thing the AI talks to) from the **Physical Transport**.
1.  Refactor `Device` in `host/core/device.py` to become a more generic base class or a class that accepts a pluggable `Postman`.
2.  Define a new class structure for `GhostDevice` that allows for "Translation Logic." A Ghost Device must be able to receive a standard Talos `INSTRUCTION` JSON and translate it into vendor-specific commands (e.g., IO Rodeo’s specific serial strings).
3.  Ensure the Ghost Device can wrap its results back into a standard Talos `DATA_RESPONSE` or `SUCCESS` message to maintain compatibility with the `incoming_message_queue`.

### Milestone 2: Driver Factory & DeviceManager Refactoring
`DeviceManager` currently assumes every connection is a standard VID/PID scan for a Talos-Pico. 
1.  Modify `DeviceManager.connect_device()` to accept an optional `driver_type` argument (e.g., `"circuitpython"`, `"io_rodeo"`, `"ghost"`).
2.  Implement a simple "Driver Factory" within the manager. When a specific driver is requested, the manager should instantiate the correct `Device` subclass and the appropriate `Postman` for that hardware.
3.  Ensure the background listener threads (`_listen_for_messages`) can still operate correctly even if the underlying transport is not a standard serial stream.

### Milestone 3: Static Device Discovery (Bypassing the Scan)
We need a way to connect to instruments that don't have a Talos-specific VID/PID.
1.  Update the logic in `DeviceManager` or `discovery.py` to allow for **Static Device Definitions**.
2.  The system should be able to read a `static_devices.json` file (or a new section in the `world_model`) that defines: `{"name": "potentiostat", "port": "COM40", "driver": "io_rodeo"}`.
3.  On startup, the `DeviceManager` should attempt to connect to these static devices first before proceeding with the standard USB discovery scan.

### Milestone 4: IO Rodeo Potentiostat Implementation (Proof of Concept)
Using the infrastructure from Milestones 1-3, implement the first Ghost Machine.
1.  Create `host/devices/io_rodeo_potentiostat.py`. 
2.  Implement a "Capability Proxy." Since this device doesn't have a native `handle_help` on a microcontroller, the Ghost Device must provide a hard-coded dictionary of `supported_commands` so the AI Planner can "discover" its features (e.g., `run_cv`, `set_voltage`).
3.  Implement the handler logic that translates the Talos `run_cv` instruction into the raw serial commands required by the IO Rodeo hardware.
4.  Verify that this device appears in the `chat.py` loop as a valid tool that the AI can include in its scientific plans.