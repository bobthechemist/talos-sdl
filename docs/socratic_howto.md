# How-To: Building New Firmware with the Socratic AI Method

This guide provides the standard workflow for creating and integrating a new instrument into the Talos-SDL framework, from design to live hardware testing.

This document assumes you have already completed the design process outlined in `docs/socratic_design_guidelines.md` and have a finished "spec sheet" for your new instrument.

## The Workflow: From Spec Sheet to Running Hardware

### Step 1: AI-Assisted Code Generation

This step uses an AI assistant to write the boilerplate firmware code.

1.  **Open the AI Prompt Template:** Use the contents of `docs/AI assistant instrument design.md` as the system prompt for your AI assistant (e.g., Gemini, ChatGPT).
2.  **Provide Context:** The prompt will ask for two inputs:
    *   **Input 1 (Software Stack):** Provide the AI with the code for `shared_lib/` and the firmware for an existing instrument (e.g., `firmware/sidekick/`). This teaches the AI the required architectural patterns.
    *   **Input 2 (Spec Sheet):** Provide the complete `socratic_<your_instrument>.md` design document you created.
3.  **Engage and Clarify:** The AI will ask clarifying questions about your instrument's hardware and desired behavior. Answer these questions to ensure the generated code is accurate.
4.  **Receive Files:** The AI will generate the three initial firmware files: `__init__.py`, `states.py`, and `handlers.py`.

### Step 2: File Placement

Place the generated files into the project structure.

1.  Create a new folder inside the `firmware/` directory. The folder name should be the name of your instrument (e.g., `firmware/stirplate_manager/`).
2.  Copy the three generated Python files into this new folder.

### Step 3: Update the Host Firmware Database

The host application needs to know how to identify your new device.

1.  **Assign an ID:** Choose a unique Product ID (PID) for your device. For internal development, use the Brockport Original Builds Vendor ID (VID) of `808`. For our example, we will assign the `stirplate_manager` a PID of `814`.
2.  **Edit the Database:** Open the file `host/firmware_db.py` and add your new device to the `products` dictionary.

    ```python
    # host/firmware_db.py

    FIRMWARE_DATABASE = {
        808: {
            'manufacturer': 'Brockport Original Builds',
            'products': {
                810: 'Fake Device',
                811: 'DIY Stirplate',
                812: 'Sidekick',
                813: 'Colorimeter',
                # --- ADD YOUR NEW DEVICE HERE ---
                814: 'Stirplate Manager'
            }
        },
    }
    ```

### Step 4: Install CircuitPython Libraries

Your new instrument firmware likely depends on specific hardware libraries that are not part of the core Talos-SDL codebase.

1.  **Identify Dependencies:** Check the `import` statements in your new `states.py` file. For the `stirplate_manager`, this is `from adafruit_motorkit import MotorKit`.
2.  **Download the Library:** Find the required library on the [CircuitPython Libraries Bundle](https://circuitpython.org/libraries) website.
3.  **Install on Device:** Connect your microcontroller. It will appear as a USB drive named `CIRCUITPY`. Copy the required library file or folder (e.g., `adafruit_motorkit.mpy`) into the `lib/` directory on the `CIRCUITPY` drive.

### Step 5: Deploy the Firmware

Use the `deploy.py` script to copy the Talos-SDL framework code and your new firmware onto the microcontroller.

1.  **Connect the Device:** Ensure your `CIRCUITPY` drive is visible on your computer. Note its drive letter (e.g., `E:` on Windows) or path.
2.  **Run the Script:** Open a terminal in the project's root directory and run the deployment script, providing the drive and your firmware's folder name.

    ```bash
    # Example for deploying the stirplate_manager to the E: drive
    python deploy.py E: stirplate_manager
    ```
3.  **What it Does:** This script will automatically:
    *   Copy the `shared_lib/` and `communicate/` folders to the device.
    *   Copy your specific `firmware/stirplate_manager/` folder.
    *   Customize the `boot.py` file on the device with the correct VID/PID (`808`/`814`).
    *   Customize the `code.py` file to import and run your new `stirplate_manager` `machine`.

### Step 6: Verification with the Control Panel

The final step is to run the host application and verify that it can communicate with your new instrument.

1.  **Launch the Host:** Run the control panel from the project root.
    ```bash
    python host/control_panel.py
    ```
2.  **Check for Success:**
    *   Click **"Scan & Connect All"**.
    *   Your new device, `Stirplate Manager`, should appear in the device dropdown list.
    *   Select the device. After a moment, its status panel should update.
    *   Periodic `TELEMETRY` messages from your device should begin appearing in the Raw Message Log.
    *   The "Available Commands" panel should populate with `set_speed` and `stop_all`.
    *   Test a command:
        *   Double-click `set_speed` to populate the command entries.
        *   Modify the arguments to `{"motor_id": 1, "speed": 0.5}`.
        *   Click **"Send"**.
        *   You should see a green `RECV_SUCCESS` message in the log confirming the command was executed.

---

Congratulations! You have successfully designed, generated, deployed, and tested a new instrument for the Talos-SDL ecosystem.