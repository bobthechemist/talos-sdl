# Core Philosophy & Features

Talos-SDL is an open-source, agentic host framework designed to lower the barrier to entry for automated scientific experimentation. It functions as a **collaborative digital peer**, empowering researchers to rapidly build bespoke robotic instruments, integrate custom sensors, and execute AI-orchestrated workflows, all while natively digitizing the data collection process.

## Core Philosophy

Our design and development are guided by several core principles:

*   **The AI as a Peer (Agentic REPL):** Researchers can interact with lab equipment through a natural-language conversational loop. An integrated LLM agent acts as a co-pilot, translating high-level scientific goals (e.g., *"Prepare a 1:1 mixture in well A1 and measure its spectrum"*) into structured, executable robotic plans.
*   **"Documentation-While-Doing":** Every human prompt, machine execution, and sensor measurement is captured and logged. The framework inherently digitizes your workflow, creating a chronological, machine-readable JSON archive ready for machine learning and total reproducibility.
*   **Human-in-the-Loop (HITL) Safety:** To mitigate AI hallucinations and ensure safe operation, Talos enforces explicit human approval prompts, strict capability validation, and optional dry-runs before physical hardware ever actuates.
*   **Plug-and-Play Hardware (Decoupled Architecture):** Talos enforces a strict separation between the "Brain" (the Python host computer) and the "Hands" (microcontrollers running your hardware). They communicate via standardized, human-readable JSON over serial, making it incredibly easy to add new DIY instruments to your lab.

## How It Works

The framework operates on a simple, transparent workflow designed to keep the scientist in control. The following diagram illustrates the flow of a typical interaction:

```mermaid
graph TD
    %% Styling
    classDef human fill:#d4edda,stroke:#28a745,stroke-width:2px;
    classDef ai fill:#cce5ff,stroke:#004085,stroke-width:2px;
    classDef system fill:#e2e3e5,stroke:#383d41,stroke-width:2px;
    classDef hardware fill:#fff3cd,stroke:#856404,stroke-width:2px;
    classDef data fill:#d1ecf1,stroke:#0c5460,stroke-width:2px;

    User[👨‍🔬 Scientist / User]:::human
    Chat[💬 Chat Interface <br/> /run or /data mode]:::system
    AI[🧠 AI Laboratory Agent]:::ai
    Orchestrator[⚙️ Lab Orchestrator <br/> Host Computer]:::system
    Instruments[🔬 Physical Instruments <br/> Sidekick Arm, Colorimeter, etc.]:::hardware
    Data[📊 Digital Lab Notebook <br/> JSON Logs & CSVs]:::data

    User -- "Natural Language Request" --> Chat
    Chat -- "Context & Constraints" --> AI
    AI -- "Proposes JSON Plan" --> Chat
    Chat -. "Human Approval" .-> User
    Chat -- "Validated Commands" --> Orchestrator
    Orchestrator -- "Executes on Hardware" --> Instruments
    Instruments -- "Telemetry & Spectral Data" --> Orchestrator
    Orchestrator -- "Registers Results" --> Data
    Orchestrator -- "Feeds Back to AI" --> AI
    AI -- "Summarizes Results" --> User
```

## The Backronym

While Talos-SDL wasn't originally designed as an acronym, it aptly describes the system's nature:

**TALOS‑SDL stands for: Transparent Abstracted Layered Orchestration System — Self‑Driving Laboratory.**

*   It is **Transparent** because every action — human, agent, or hardware — is logged chronologically and made visible.
*   It is **Abstracted** because hardware, firmware, capabilities, and vendor details are hidden behind uniform digital twins and protocols.
*   It is **Layered** because the architecture is a vertically tiered stack of reasoning, planning, control, firmware, and hardware subsystems.
*   It is an **Orchestration System** because it coordinates these layers coherently, deterministically, and safely.
*   And it serves a **Self‑Driving Laboratory,** enabling autonomous experimentation while maintaining safety, reproducibility, and modularity.


