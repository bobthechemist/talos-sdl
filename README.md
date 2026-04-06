# Talos-SDL Orchestrator

**An open-source, agentic host framework for Self-Driving Laboratories (SDLs) and autonomous experimentation.**

Talos-SDL is designed to lower the barrier to entry for automated scientific experimentation. It functions as a **collaborative digital peer**, empowering researchers to rapidly build bespoke robotic instruments, integrate custom sensors, and execute AI-orchestrated workflows—all while natively digitizing the data collection process.

## Why Talos-SDL?

Talos-SDL embodies a core philosophy of **AI as a Peer**, enabling natural-language interaction with your lab equipment. It emphasizes **"Documentation-While-Doing"** for total reproducibility and incorporates **Human-in-the-Loop (HITL) Safety** to ensure secure operation. With its **Plug-and-Play Hardware** architecture, adding new DIY instruments to your lab is remarkably straightforward.

For a deeper dive into the project's philosophy and features, please visit the [Core Philosophy & Features documentation](docs/concepts/core_philosophy_features.md).

## Project Structure

The repository is organized to separate the high-level AI logic from the low-level hardware control:

*   `host/`: The "Brain." Contains the Python application that runs on your PC. Includes the AI agentic loop (`ai/`), graphical user interfaces (`gui/`), and device management logic.
*   `firmware/`: The "Hands." Contains the CircuitPython code that runs on your microcontrollers (e.g., Raspberry Pi Pico). Includes specific modules for the `sidekick` robotic arm, `colorimeter`, and common libraries.
*   `shared_lib/`: Shared protocols and message definitions to ensure the Host and Firmware speak the exact same language.
*   `docs/`: Comprehensive documentation for users and developers, including architectural deep-dives, design protocols, and tutorials.

## Getting Started

To get started with Talos-SDL, follow these quick steps. For detailed instructions on setting up your environment, deploying firmware, and building your own instruments, refer to our full [Building Your First Instrument Firmware tutorial](docs/tutorials/building_your_first_firmware.md).

### 1. Host Setup
Clone the repository and install the required Python packages in a virtual environment:
```bash
git clone https://github.com/yourusername/talos-sdl.git
cd talos-sdl
python -m venv .venv
./.venv/Scripts/activate
pip install -r requirements.txt
```

### 2. Deploying Firmware (Example: Sidekick)
Connect your CircuitPython device (it should appear as a USB drive named `CIRCUITPY`). Use the included deployment script to load the instrument's firmware onto the board.

For example, to deploy the Sidekick robotic arm firmware to drive `D:`:
```bash
python deploy.py D: sidekick
```

### 3. Enter the Laboratory Cockpit
To start the AI-driven conversational loop, run the chat interface:
```bash
python host/ai/chat.py
```
*Tip: Type `/help` once inside the interface to see available commands, switch between `/run` (hardware control) and `/data` (analysis) modes, and view registered datasets.*

Alternatively, if you prefer to drive the lab manually without AI, you can launch the graphical user interface:
```bash
python host/control_panel.py
```

## Documentation

For comprehensive guides, API references, design protocols, and more, explore the full [Talos-SDL Documentation](docs/index.md).

## License

This project is licensed under the [MIT License](LICENSE).