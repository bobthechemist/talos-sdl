# **Talos-SDL:** Host Design Protocol (Version 1.0)

This document would define the architecture for all PC-side applications that control the Self-Driving Laboratory.

## **1. Guiding Principles**

The Host World operates on four core principles that ensure stability and scalability:

*   **Separation of Concerns:** The code responsible for the user interface (the "View") is strictly separated from the core application logic (the "Controller") and the representation of device state (the "Model"). This is the essence of the MVC pattern.
*   **Centralized Device Management:** A single, authoritative component (the `DeviceManager`) is responsible for discovering, connecting to, and communicating with all hardware. No other part of the application should ever create its own `SerialPostman`.
*   **Asynchronous Communication:** The host application must never "block" or "freeze" while waiting for a device to complete a task. All communication is asynchronous. Commands are sent, and responses are processed as they arrive.
*   **Abstraction:** The host application should not need to know the low-level details of *how* an instrument performs a task. It should only know *what* commands the instrument accepts. The instrument is treated as a "black box" with a clearly defined API (its `help` command).

## **2. The Core Architecture: Model-View-Controller (MVC)**

All host applications MUST be built around the three core components found in `host_app/core/`.

*   **The Model (`host_app/core/device.py`):**
    *   **Role:** The "Digital Twin." A `Device` object is the host's in-memory representation of a single physical instrument.
    *   **Responsibilities:**
        *   Holds the state of the device (port, VID/PID, firmware name, version, last-known state, latest telemetry data, etc.).
        *   Is completely UI-agnostic. It knows nothing about buttons or windows.
        *   Is responsible for updating its own state based on incoming messages (`update_from_message` method).

*   **The Controller (`host_app/core/device_manager.py`):**
    *   **Role:** The "Orchestrator" or "Middle Manager." The `DeviceManager` is the brain of the host-side operations.
    *   **Responsibilities:**
        *   Manages the entire lifecycle of all `Device` objects (the Models).
        *   Scans for, connects to, and disconnects from physical hardware.
        *   Runs the background listener threads for each device to receive messages.
        *   Provides a single, unified interface for sending messages to any connected device (`send_message` method).
        *   Manages the central `incoming_message_queue` where all messages from all devices are placed for processing.

*   **The View (`host_app/gui/main_view.py`):**
    *   **Role:** The "Face." This is the graphical user interface that the human operator interacts with.
    *   **Responsibilities:**
        *   Displays the data contained within the `Device` models.
        *   Translates user actions (like button clicks) into commands that are sent to the `DeviceManager` (the Controller).
        *   **Crucially, the View NEVER talks to a `Device` model directly.** It only ever communicates with the `DeviceManager`. This is the key to maintaining separation of concerns.

## **3. The Two "Clients" of the Core Architecture**

The MVC core is the stable foundation. The protocol must define how different types of applications ("clients") can use this foundation.

*   **Client 1: The Human-in-the-Loop (The GUI Application)**
    *   **Implementation:** `run_mvc_app.py`
    *   **Protocol:** This client instantiates the `DeviceManager` and the `MainView`. It links them together, allowing the user to drive the laboratory through a visual interface. The flow is always **User -> View -> Controller -> Model**.

*   **Client 2: The Autonomous Agent (Scripts and AI)**
    *   **Implementations:** `scanning_colorimeter.py`, `vertext_test.py`, `test_phase2_backend.py`
    *   **Protocol:** This is where the protocol needs to be formalized.
        *   **DEPRECATED PATTERN:** Scripts like `scanning_colorimeter.py` currently create their own `SerialPostman`. This is now considered an anti-pattern because it bypasses the centralized state management and logging of the `DeviceManager`. It creates a "rogue agent" that the rest of the system is unaware of.
        *   **REQUIRED PATTERN:** All future scripts, whether for simple automation or complex AI control, **MUST** use the `DeviceManager` as their entry point to the lab. The `test_phase2_backend.py` script is the perfect example of this correct pattern.

**A compliant autonomous script workflow:**
1.  Instantiate `DeviceManager`.
2.  Use `manager.scan_for_devices()` and `manager.connect_device()` to establish connections.
3.  Send commands using `manager.send_message()`.
4.  Process responses by reading from the `manager.incoming_message_queue`. This allows the script to get all the rich, parsed message data without having to manage its own listener thread.
5.  When finished, call `manager.stop()` to gracefully close all connections.

## **4. Why This Protocol is Critical for AI**

By enforcing that AI agents use the same `DeviceManager` as the GUI, you gain several massive advantages:

1.  **Consistency:** The AI interacts with the lab using the exact same API as a human user. There is no special "AI backdoor."
2.  **Human-in-the-Loop Supervision:** You can build an advanced GUI that **visualizes the state of the `Device` models** while an AI script is running. The GUI and the AI script are both observing the same "source of truth." This allows a human to monitor, pause, or override an AI agent's actions.
3.  **Simplified AI Logic:** The AI agent's job is simplified. It doesn't need to worry about low-level serial communication or threading. It only needs to focus on three things:
    *   Choosing which device to use (`manager.devices`).
    *   Constructing the correct `Message` payload.
    *   Sending the message via `manager.send_message()`.

