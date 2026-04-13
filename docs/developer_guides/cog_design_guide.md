## Documentation: Designing a New Cog

### 1. Our Design Philosophy

A "Cog" is a modular tool that extends the capabilities of the `talos-sdl` Cockpit. This system allows you to build domain-specific tools (like a plate manager or a calibration wizard) that are only present when needed.

*   **Slash-Command Driven:** Cogs expose functionality via slash commands (e.g., `/run`, `/data`, `/my_tool`), making the Cockpit a clean, command-based interface.
*   **Encapsulation of Concerns:** A Cog should have a single focus. A `run_cog` handles execution; a `data_cog` handles RAG and analysis. Do not mix disparate responsibilities.
*   **Stateless Execution:** Cogs should generally be stateless. State information (like the current well-plate arrangement or experimental progress) belongs in the `dln` (Digital Lab Notebook).
*   **Dynamic Loading:** Cogs are loaded based on the `world_model.json`. This ensures the Cockpit remains relevant to the specific hardware connected.

### 2. The Cog Anatomy (The File-System Blueprint)

To create a new slash command (e.g., `/my_tool`), you must create exactly **one file** in the `host/cogs/` directory.

**File Location:** `host/cogs/my_tool_cog.py`

This file encapsulates the class that interfaces with your instrument or logic. It must contain:
1.  **Imports:** Your dependencies (e.g., `from host.cogs.base_cog import BaseCog`).
2.  **The Class Definition:** A class that inherits from `BaseCog`.
3.  **Command Mapping:** A `get_commands()` method that tells the Cockpit which slash commands you are adding.
4.  **Handler Methods:** The actual logic that runs when the user types the command.

### 3. Step-by-Step Implementation Guide

#### Step 1: Define the Blueprint (The Design Template)
Create a file named `host/cogs/my_tool_cog.py` and implement the following structure:

```python
from host.cogs.base_cog import BaseCog
from host.gui.console import C

class MyToolCog(BaseCog):
    """
    Description of what this cog does for the researcher.
    """

    def get_commands(self):
        """Register your slash commands here."""
        return {
            "/my_tool": self.handle_my_tool
        }

    def handle_my_tool(self, *args):
        """Description of the command for the /help menu."""
        # 1. Parse arguments (args is a tuple of strings)
        # 2. Query the DLN if you need state
        # 3. Perform the logic
        # 4. Print results to console using C.OK / C.ERR
        print(f"{C.OK}My Tool executed successfully!{C.END}")
```

#### Step 2: Register in `world_model.json`
The Cockpit won't know your cog exists until you tell it to load. Open `world_model.json` and add your file name (without the `.py`) to the appropriate list:

*   **For core tools:** Add to `"required_cogs"`.
*   **For instrument-specific tools:** Add to `"contextual_cogs"`.

```json
{
  "required_cogs": ["core_cog", "ai_cog", "run_cog", "data_cog", "my_tool_cog"]
}
```

#### Step 3: Implement Logic & DLN Integration
If your tool needs data, use the `self.dln` reference provided by the `BaseCog`.

*   **To read data:** Use `self.dln.query_relational(sql)` or `self.dln.query_vector(query, session_id)`.
*   **To write data:** Use `self.dln.log_science(...)`.
*   **To handle binaries:** Use `self.dln.store_blob(...)` to save the file and `log_science` to store the resulting reference path as a "blob_reference" type.

### 4. Implementation Checklist

- [ ] **Naming:** Does the filename end in `_cog.py`?
- [ ] **Class Name:** Does the class inherit from `BaseCog`?
- [ ] **Registration:** Is the command string in `get_commands()` prefixed with a `/`?
- [ ] **Arguments:** Does your handler take `*args` to safely accept user input?
- [ ] **Feedback:** Does the handler use `print()` with `C.OK`, `C.WARN`, or `C.ERR` colors so the user knows if the command succeeded?
- [ ] **Registry:** Is the cog name added to `world_model.json`?

### 5. Contextual Loading

If you are building a tool for a specific instrument, name your file accordingly (e.g., `sidekick_tools_cog.py`). By adding it to the `"contextual_cogs"` section of `world_model.json` mapped to the device trigger (e.g., `"sidekick": "sidekick_tools_cog"`), the system will only load it if that device is physically connected. This keeps your interface clean and avoids command clutter for hardware that isn't present.