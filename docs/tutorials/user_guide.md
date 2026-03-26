# Talos-SDL User Guide: Operating Your Self-Driving Laboratory

Welcome to the Talos-SDL User Guide! This document will walk you through the process of setting up, interacting with, and interpreting results from your agentic self-driving laboratory. Whether you're executing predefined experiments or exploring new chemistry with AI assistance, this guide provides the essential knowledge to operate Talos-SDL effectively and safely.

## 1. What is Talos-SDL?

Talos-SDL is an open-source framework that transforms your laboratory into an autonomous experimentation platform. At its core, it's designed to be your **collaborative digital peer**, enabling you to:

*   **Interact Naturally:** Use everyday language to instruct your lab equipment.
*   **Automate Complex Workflows:** Translate high-level scientific goals into precise robotic actions.
*   **Ensure Reproducibility:** Automatically log every action and measurement.
*   **Maintain Safety:** Keep humans in control with explicit approval steps.

For a deeper understanding of the project's foundational ideas, please refer to the [Core Philosophy & Features documentation](../concepts/core_philosophy_features.md).

## 2. Initial Setup: Getting Your Lab Ready

Before you can command your instruments, ensure your environment is set up correctly.

### 2.1. System Prerequisites

You'll need:

*   A PC (Windows, macOS, Linux) running **Python 3.8+**.
*   An **API key** for a supported Large Language Model (LLM) provider (e.g., Google Gemini, OpenAI, Anthropic). This key should be set as an environment variable (e.g., `GOOGLE_API_KEY` for Gemini).
*   One or more **CircuitPython-compatible microcontrollers** (e.g., Raspberry Pi Pico, Adafruit Feather) connected to your physical instruments (e.g., Sidekick robotic arm, Colorimeter). These devices should appear as a USB drive named `CIRCUITPY`.
*   The necessary **CircuitPython libraries** installed on your microcontrollers for your specific hardware (e.g., `adafruit_as7341.mpy` for the Colorimeter).

### 2.2. Software Installation

1.  **Clone the Repository:** If you haven't already, get the Talos-SDL code:
    ```bash
    git clone https://github.com/bobthechemist/talos-sdl.git
    cd talos-sdl
    ```

2.  **Install Python Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Deploy Firmware to Your Instruments:** Each physical instrument needs to run its specific Talos-SDL firmware.
    *   Connect your CircuitPython device. It should appear as a USB drive named `CIRCUITPY`.
    *   Use the `deploy.py` script. For example, to deploy the Sidekick robotic arm firmware to drive `D:` (Windows) or `/Volumes/CIRCUITPY` (macOS/Linux):
        ```bash
        python deploy.py D: sidekick
        ```
        *(Replace `D:` with your device's actual drive letter/path, and `sidekick` with the name of the firmware folder in `firmware/`.)*
    *   **Important:** After deploying firmware, always **power cycle** your microcontroller (unplug and replug it) for changes to `boot.py` and `code.py` to take effect.

For a detailed walkthrough on setting up your environment and deploying firmware, see the [Building Your First Instrument Firmware tutorial](building_your_first_firmware.md).

## 3. The Laboratory Cockpit: AI-Driven Interaction (`host/ai/chat.py`)

The primary way to interact with your Talos-SDL system is through the AI-driven conversational loop, which we call the "Laboratory Cockpit."

### 3.1. Launching the Cockpit

From the project's root directory, run:

```bash
python host/ai/chat.py
```

Upon launching, the system will:
1.  **Load the World Model:** It will attempt to load `job_world.json` if present, or fall back to a default configuration. This model tells the AI what reagents are in which pumps, the maximum well volume, etc.
2.  **Scan and Connect Devices:** It will automatically scan your system for connected Talos-SDL instruments (Sidekick, Colorimeter, Stirplate Manager, etc.) and establish communication.
3.  **Initialize AI Agents:** It sets up the AI models for both "run" (control) and "data" (analysis) modes.

### 3.2. Understanding Modes: `/run` and `/data`

The Laboratory Cockpit operates in two distinct modes to ensure clarity and safety:

*   **`/run` (Laboratory Controller):** This is the **default mode** for controlling your physical hardware.
    *   In this mode, the AI's primary goal is to generate **JSON plans** consisting of hardware commands.
    *   **Human confirmation is required** by default before any physical actions are taken.
    *   The prompt indicator will be `[RUN 🔒] >` (or `[RUN ⚡] >` if confirmation is off).
*   **`/data` (Data Analyst):** This mode is for analyzing and interpreting experimental data.
    *   In this mode, the AI **cannot** issue any hardware commands.
    *   It responds in natural language and can perform summaries, identify trends, and answer questions about datasets.
    *   The prompt indicator will be `[DATA ✅] >`.

### 3.3. Key Slash Commands

Type a slash (`/`) followed by the command to interact with the cockpit:

*   **`/help`**: Displays a list of all available slash commands and their descriptions.
*   **`/run [your goal here]`**: Switches to "run" (Controller) mode. If you provide a goal after `/run`, the AI will immediately try to generate a plan for it.
*   **`/data [your query here]`**: Switches to "data" (Analyst) mode. If you provide a query after `/data`, the AI will try to answer it using available context and datasets.
*   **`/confirm [on|off]`**: Toggles the human confirmation step before executing an AI-generated plan.
    *   `on`: (Default) You must type `y` or `run` to approve a plan. `[RUN 🔒] >`
    *   `off`: Plans execute immediately after AI generation. `[RUN ⚡] >`
    *   **Warning:** Use `/confirm off` with extreme caution, especially with physical hardware.
*   **`/datasets`**: Lists all recorded datasets from the current session. Each dataset is assigned a unique `ds_YYYYMMDD_HHMMSS` ID.
*   **`/log`**: Saves the current conversational session and all executed plans/results to a JSON log file in the `temp/` directory.
*   **`/clear`**: Clears the AI's short-term conversational history for the *current mode*.
*   **`/quit`** (or `/exit`): Shuts down the Laboratory Cockpit, disconnects devices, and saves the session log.

### 3.4. Interacting in `/run` Mode (Controller)

1.  **State Your Goal:** Type your desired scientific action in natural language (e.g., "Home the robotic arm," "Add 100 µL of acetic acid to well A1," "Measure the spectrum of well H5").
2.  **AI Proposes a Plan:** The AI will process your request and propose a JSON-formatted plan consisting of one or more device commands.
    ```json
    {
      "plan": [
        {"device": "sidekick", "command": "to_well", "args": {"well": "A1", "pump": "p1"}},
        {"device": "sidekick", "command": "dispense", "args": {"pump": "p1", "vol": 100.0}}
      ]
    }
    ```
3.  **Human-in-the-Loop Approval:**
    *   If `/confirm` is `on` (default), you will be prompted to review the plan.
    *   You can type `y` or `run` to approve, `n` or `reject` to cancel, `del <#>` to remove a specific step, or `edit <#>` to modify the arguments of a step.
    *   This is your critical safety gate. Always review plans carefully!
4.  **Execution & Feedback:**
    *   Once approved, the system executes each command in the plan sequentially.
    *   You'll see real-time updates on the command's status (`[OK]`, `[PROBLEM]`).
    *   If a command returns data (e.g., a colorimeter measurement), the system will perform a **one-shot analysis**: a brief, natural-language summary of the data relevant to your goal, without switching modes.

### 3.5. Interacting in `/data` Mode (Analyst)

1.  **Switch to Data Mode:** Type `/data` to switch modes. The prompt will change to `[DATA ✅] >`.
2.  **Query Data:** Ask questions about your experiments or recorded datasets.
    *   "What did I dispense into well A1?"
    *   "Can you summarize the spectrum from dataset `ds_20260220_124909`?"
    *   "Compare the yellow channel intensity between `ds_12345` and `ds_67890`."
3.  **Dataset Content Injection:** If your query includes a valid dataset ID (e.g., `ds_YYYYMMDD_HHMMSS`), the system will automatically load the raw JSON content of that dataset into the AI's context before processing your question.
4.  **AI Analysis:** The AI will use its analytical capabilities and the provided data to answer your questions in natural language.

## 4. Manual Control: The Graphical User Interface (`host/control_panel.py`)

For direct, manual control of individual devices without AI assistance, you can use the graphical user interface.

### 4.1. Launching the Control Panel

From the project's root directory, run:

```bash
python host/control_panel.py
```

### 4.2. Basic Operations

*   **Scan & Connect All:** This button will scan for all connected Talos-SDL devices and establish serial connections.
*   **Select Device:** Use the dropdown menu to choose which connected instrument you want to control.
*   **Device Status Panel:** Displays firmware name, version, and the latest telemetry data from the selected device.
*   **Available Commands:** A list of all commands supported by the *selected device*. Double-click a command to populate the "Function" and "Arguments" fields below.
*   **Send Command:**
    *   Enter the `Function` name (e.g., `set_speed`).
    *   Enter `Arguments` as a JSON dictionary (e.g., `{"motor_id": 1, "speed": 0.5}`). Remember that string values **must** be in double quotes (e.g., `pump:"p1"`).
    *   Click **Send** to dispatch the command.
*   **Raw Message Log:** Displays all incoming and outgoing messages in real-time, color-coded by type (Sent, Received Success, Problem, Telemetry, etc.).

## 5. Understanding Your Data & Logs

Talos-SDL is designed for "Documentation-While-Doing."

*   **Session Logs (`temp/chat-session-*.json`):** Every interaction in the Laboratory Cockpit is recorded in a timestamped JSON file. This log includes your prompts, the AI's plans, human approvals, execution results, and any generated one-shot analyses. These are invaluable for reviewing experiments and debugging.
*   **Registered Datasets (`temp/data/ds_*.json`, `temp/data/ds_*.csv`):** Any `DATA_RESPONSE` message from an instrument (e.g., a spectral measurement) is automatically saved to disk by the `Registry`. It stores both a raw JSON file and, if possible, a CSV version for easy analysis. Each dataset gets a unique ID (`ds_YYYYMMDD_HHMMSS`). You can list these with the `/datasets` command in the cockpit.

## 6. Troubleshooting Common Issues

*   **"Device not found" or connection errors:**
    *   Ensure your microcontroller is plugged in and recognized by your computer.
    *   Verify the correct firmware is deployed and the microcontroller has been power cycled.
    *   Check your `host/firmware_db.py` to ensure your device's VID/PID pair is registered.
    *   Confirm no other application is using the serial port (e.g., another instance of `chat.py` or a serial monitor).
*   **AI produces "PROBLEM" messages:**
    *   Carefully read the error message in the payload. It often indicates invalid arguments, a device in the wrong state (e.g., not homed), or a hardware fault.
    *   Check the relevant [Design Protocols](../design_protocols/firmware_design_protocol.md) and [API Reference](../api/firmware.md) for the device's commands to ensure correct usage.
*   **Mermaid diagrams not rendering:** Ensure you have `pymdown-extensions` installed (`pip install pymdown-extensions`) and your `mkdocs.yml` is configured correctly for `pymdownx.superfences`.

## 7. Next Steps: Beyond Basic Operation

Once you're comfortable operating the lab, you might want to:

*   **Build Your Own Instruments:** Learn how to integrate new custom hardware into the Talos-SDL ecosystem using the [Building Your First Instrument Firmware tutorial](building_your_first_firmware.md) and the [Socratic Design Method developer guide](../developer_guides/socratic_design_method.md).
*   **Explore Advanced AI Capabilities:** Dive into the `host/ai/` codebase to understand how the AI agent learns and plans.
*   **Contribute to Talos-SDL:** Check out the [developer guides](../developer_guides/coding_style_guide.md) and [design protocols](../design_protocols/firmware_design_protocol.md) if you're interested in extending the framework itself.

Happy experimenting!