## Documentation: Designing a New Cog

### 1. Our Cog Philosophy

A "Cog" is a modular tool that extends the capabilities of the `talos-sdl` Cockpit. While the `StateMachine` handles hardware, the Cog system handles *intent, logic, and integration*. The core principles are:

*   **Slash-Command Driven:** Cogs expose functionality via slash commands (e.g., `/run`, `/data`, `/model`), making the Cockpit a true "Command Center."
*   **Encapsulation of Concerns:** A Cog should have a single focus. A `run_cog` handles hardware planning; a `data_cog` handles RAG and analysis. Do not mix disparate responsibilities.
*   **Stateless Execution:** Cogs should generally be stateless. State information (like the current well-plate arrangement or an experiment's progress) belongs in the `dln` (Digital Lab Notebook).
*   **Dynamic and Contextual:** Cogs can be loaded based on the `world_model.json`. This ensures the Cockpit remains light and relevant to the specific hardware connected.

### 2. The Design Process: A Question-Driven Approach

Designing a cog requires thinking about how your tool interacts with the AI, the user, and the data.

#### Step 1: Definition and Scope

Answer these questions to define the "What" and "Why" of your Cog:

1.  **What is the primary role of this Cog?** (e.g., "To manage hardware execution," "To perform specialized data visualization.")
2.  **What slash commands will it expose?** (e.g., `/run`, `/liveview`, `/calibrate`).
3.  **Does it need access to specific hardware?** (If so, specify the hardware trigger that should cause it to load).
4.  **How does it interact with the DLN?** (Does it read observations? Does it log new analysis? Does it store blobs?).

#### Step 2: The Command API

Define the interface for your slash commands. For each command:

*   **Command Name:** Must start with a `/`.
*   **Description:** A concise summary (this is used by the Cog to auto-generate the `/help` menu).
*   **Handler Method:** The logic that executes when the user triggers the command.
*   **AI Access:** Will the AI agent need to call this command internally? (If yes, you must ensure the logic is robust and error-resistant).

#### Step 3: State and Data Strategy

How will your Cog store and retrieve information?

*   **If it's temporary configuration:** Store it in the Cog instance variables.
*   **If it's experimental data:** Do NOT store it in the Cog. Use `dln.log_science()` or `dln.store_blob()` to ensure the data is immutable and traceable.
*   **If it's structural (like well contents):** Query the `dln` for past logs to reconstruct state. Do not use local dictionaries that reset when the program restarts.

### 3. The Design Document Template

Copy this template into a new file and fill it out before starting your Cog implementation.

---

## Cog Design: [Cog Name]

### 1. Cog Overview

*   **Primary Purpose:** [Short description]
*   **Primary Slash Commands:** [/cmd1, /cmd2]
*   **Hardware Trigger:** [e.g., 'sidekick', or 'none' if it is a core cog]
*   **DLN Interaction:** [e.g., "Reads observation logs," "Logs reflection entries."]

### 2. Command Interface

| Command | Description | Handler Function | AI-Internal |
| :--- | :--- | :--- | :--- |
| `/example` | Performs a test. | `handle_example()` | [Yes/No] |

### 3. Workflow Design

*(Answer these for your primary slash command)*

1.  **Input:** What does the user/AI provide as arguments?
2.  **Process:** What steps occur? (e.g., "Parse arguments," "Query DLN," "Format data for LLM.")
3.  **Output:** What is the result? (e.g., "Print Markdown table to console," "Return JSON to AI agent.")
4.  **Error Handling:** What happens if the input is malformed or if the requested data isn't in the DLN?

### 4. Implementation Checklist

- [ ] Does the Cog inherit from `BaseCog`?
- [ ] Is the `get_commands()` method correctly mapping slash commands to handlers?
- [ ] Are any large data outputs logged to the DLN as `blob_reference`?
- [ ] Is the `world_model.json` updated with this cog name in the `required_cogs` or `contextual_cogs` list?

---

### 4. Best Practices for Developers

*   **Keep Handlers Lean:** If a handler logic grows beyond 50 lines, it belongs in a helper method or a separate service class.
*   **Use the Console Utility:** Always import `host.gui.console.C` to provide clear, color-coded feedback to the user.
*   **Leverage the `dln`:** Treat the `dln` as your database of record. If your Cog "forgets" information, it’s a sign that you should be querying the notebook instead of keeping variables in memory.
*   **Human-In-The-Loop:** If a Cog modifies hardware or changes experimental state, ensure there is a confirmation gate.