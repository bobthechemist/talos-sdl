# SOP-DEV-01: Integration of New Agentic Instruments

**Purpose:** To define the formal process for integrating a new hardware instrument into the Talos-SDL ecosystem, shifting the developer's role from manual coding to "Context Provider" for AI-assisted generation.
**Scope:** Covers hardware identification, registry update, agentic firmware development, and deployment.

---

## 1. Prerequisites and Setup
1.1. Ensure the Target Microcontroller is flashed with the latest **CircuitPython** (v9.x+).  
1.2. **Assign USB Identification:** Identify or assign a unique Vendor ID (VID) and Product ID (PID) pair.
*   Values must be unsigned 16-bit integers (0 to 65535).
*   **Standard Practice:** Use Hexadecimal notation (e.g., `0x2E8A`).
*   *Note:* The pair must be unique within your laboratory to allow the `DeviceManager` to differentiate tools.

---

## 2. Host-Side Registry Update
2.1. Open `host/firmware_db.py`.  
2.2. Add a entry to the `FIRMWARE_DATABASE`. 
*   **Maker Pi Example:**
    ```python
    0x2E8A: { 
        'manufacturer': 'Cytron Technologies',
        'products': {
            0x0814: "Alert Module"
        }
    }
    ```
2.3. **Folder Naming:** Choose a short, lowercase "slug" for your firmware folder (e.g., `alert_module`). This name will be used for the directory in Step 4.

---

## 3. The Socratic Design Phase
3.1. **Prepare Workspace:** Ensure the directory `.talos/specs/` exists in your project root.
*   *Note:* The `.talos` folder may be hidden by your OS. Create it manually if it has not been created by a previous session.
3.2. **Copy Template:** Copy `docs/design_protocols/design_examples/spec_template.md` to `.talos/specs/[slug]_spec.md`.
3.3. **Complete Spec Sheet:** Fill out the document to define the "Logical Blueprint" of the instrument.
*   Define the `CONFIG` dictionary with physical pin mappings.
*   Define the Command Interface table (`func`, `args`, `ai_enabled`).
*   **Constraint:** Do not include I2C pins (SCL/SDA) unless the firmware actually instantiates an I2C bus object.

---

## 4. Agentic Firmware Generation
4.1. **Prepare the Prompt:** 
*   Copy `docs/developer_guides/ai_agent_prompt_templates/firmware_generation_template.md` to your workspace as `.talos/specs/[slug]_prompt.txt`.
*   Insert the **Firmware Codebase Context** (Input 1) and your **Spec Sheet** (Input 2) into the template placeholders.

4.2. **The Socratic Coding Session:**
*   Provide the assembled prompt content to a high-reasoning LLM (e.g., Gemini 1.5 Pro).
*   **CRITICAL GUARDRAIL:** If the AI generates code immediately without asking questions, **STOP IT**. Command the AI: *"You skipped the clarification step. Review the spec sheet and ask the required clarifying questions regarding pin behavior, timing, and state transitions before providing code."*
*   Answer all clarifying questions to prevent hardware hallucinations (like incorrect `board` attributes).

4.3. **File Creation:**
*   Create the directory: `firmware/[slug]/` (using the name from Step 2.3).
*   Paste the AI-generated code into `__init__.py`, `handlers.py`, and `states.py`.

---

## 5. Deployment and Commissioning
5.1. **Configure Main Entry:** Update `firmware/common/code.py` to import your new subsystem:
```python
from firmware.[slug] import machine
```
5.2. **Run Deployment:** Use the deployment script to push the code to the microcontroller:
```bash
# Example syntax:
python deploy.py [DRIVE_LETTER]: [SLUG]
```
5.3. **Apply Settings:** Physically unplug and replug the device. A standard reset button press is often insufficient to apply `boot.py` USB identification changes.

---

## 6. Validation and Diagnostics
6.1. **Diagnostic Check (Hardware Level):**
*   Open **Thonny** or a serial terminal and connect to the **CircuitPython Console/REPL port**.
*   Verify no tracebacks appear on boot. If the firmware crashes (e.g., `AttributeError`), the error will be visible here.

6.2. **Manual Check (Controller Level):**
*   Run `python host/control_panel.py` and click **"Scan & Connect All"**.
*   Select your tool from the dropdown. 
*   Verify `TELEMETRY` messages appear in the log and test a single command to confirm a `SUCCESS` response.

6.3. **Agentic Check (Peer Level):**
*   Run `python host/ai/chat.py`.
*   Confirm the AI logs: `[+] Received capabilities from [slug]`.
*   **Test Prompt:** Provide a goal (e.g., *"Flash a red light to show you are initialized"*) and verify the AI generates the correct JSON plan using your specific commands.

---

### Action Items & Todo List
*   [ ] **Toolbox Architecture:** Review the chat routine to ensure it remains firmware-independent; design a "Toolbox" mechanism for host-side helper code.
*   [ ] **Prompt Engineering:** Hardened "STOP/WAIT" instructions in `firmware_generation_template.md`.
*   [ ] **Tooling:** Develop `firmware-context.py` (slim all-in-one script) for token-efficient context.
*   [ ] **Code (Deploy Refactor):** Update `deploy.py` to copy only target folder + `common/`; fix Hex-to-Int comparison in `get_firmware_name_by_vid_pid`.
*   [ ] **Documentation:** Update `socratic_design_method.md` to point to `spec_template.md` as the single source of truth.

