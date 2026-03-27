# Talos-SDL Documentation

Welcome to the documentation for the Talos-SDL Orchestrator – an open-source, agentic host framework for Self-Driving Laboratories (SDLs) and autonomous experimentation.

This documentation serves as your guide to understanding, operating, and extending Talos-SDL, designed to empower researchers to rapidly build bespoke robotic instruments, integrate custom sensors, and execute AI-orchestrated workflows. Talos-SDL is designed with rapid prototyping and deployment in mind and targets single users and small groups interested in exploring agentic scientific laboratory instrumentation.

>Much of this documentation is in *draft* form and has been written by AI based on the codebase and journals the developer has kept during the framework design process. Revisions and review are in process.

## Documentation Sections

Explore the different facets of Talos-SDL:

*   **[Tutorials](tutorials/user_guide.md)**: Step-by-step guides for users to operate the system and for new developers to get started with firmware creation.
*   **[Concepts](concepts/architecture_overview.md)**: High-level overviews of the project's core philosophy, features, and overall architectural design.
*   **[Developer Guides](developer_guides/coding_style_guide.md)**: Practical guides, best practices, and templates for developers looking to extend, modify, or contribute to the Talos-SDL framework.
*   **[Design Protocols](design_protocols/communication_protocol.md)**: Formal specifications and normative guidelines for how various components and systems within Talos-SDL are designed and expected to behave.
*   **[API Reference](api/communicate.md)**: Technical documentation automatically generated from the Python source code, detailing classes, methods, and functions.

## Project Structure

The repository is organized to separate the high-level AI logic from the low-level hardware control, ensuring modularity and maintainability:

*   **`host/`**: The "Brain." Contains the Python application that runs on your PC, including AI agents, graphical user interfaces, and device management logic.
*   **`firmware/`**: The "Hands." Contains the CircuitPython code that runs on your microcontrollers, tailored for specific instruments like the `sidekick` robotic arm or `colorimeter`.
*   **`communicate/`**: The "Language." Contains the abstracted classes and code to ensure communication between host, firmware, and other devices follow well-formatted constructs.
*   **`shared_lib/`**: Common protocols, utilities, and message definitions that ensure consistent communication and behavior across both host and firmware.
*   **`docs/`**: This documentation! Containing all guides, concepts, protocols, and API references.