graph TD
    %% Styling
    classDef human fill:#d4edda,stroke:#28a745,stroke-width:2px;
    classDef ai fill:#cce5ff,stroke:#004085,stroke-width:2px;
    classDef system fill:#e2e3e5,stroke:#383d41,stroke-width:2px;
    classDef hardware fill:#fff3cd,stroke:#856404,stroke-width:2px;
    classDef data fill:#d1ecf1,stroke:#0c5460,stroke-width:2px;

    User[👨‍🔬 Scientist / User]:::human
    Chat[💬 Chat Interface </br> /run or /data mode]:::system
    AI[🧠 AI Laboratory Agent]:::ai
    Orchestrator[⚙️ Lab Orchestrator </br> DeviceManager & PlateManager]:::system
    Instruments[🔬 Physical Instruments </br> Sidekick & Colorimeter]:::hardware
    Data[📊 Digital Lab Notebook </br> JSON Logs & CSVs]:::data

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