# Talos-SDL: Communication Protocol and the Postman Pattern

This document outlines the standardized communication protocol and the **Postman Pattern** employed in the Talos-SDL framework. This architecture is crucial for abstracting the complexities of inter-process communication between the host computer (running Python) and the microcontroller-based instruments (running CircuitPython).

## Introduction

The Talos-SDL framework operates across diverse computing environments: a powerful host computer for orchestration and AI, and resource-constrained microcontrollers for direct hardware control. These environments utilize different underlying communication mechanisms (e.g., `pyserial` on the host, `usb_cdc.data` on CircuitPython). To ensure flexible, testable, and robust message exchange, an abstraction layer is necessary to decouple high-level application logic from low-level transport specifics.

## The Postman Pattern

The **Postman Pattern** defines a clear, abstract interface for sending and receiving messages over any communication channel. In this pattern:

*   **The Postman:** Handles the low-level mechanics of message transport. This includes actions like opening and closing a serial port, encoding/decoding data, writing bytes, and reading incoming lines. Each specific communication medium (e.g., standard serial, CircuitPython's USB CDC data channel, or a dummy channel for testing) will have its own concrete `Postman` implementation.
*   **The Clients (Secretary/DeviceManager):** High-level components like the `DeviceManager` on the host or the `StateMachine` (acting as a "Secretary" on the device) *use* an instance of a `Postman` to communicate. These clients interact with the standardized `Postman` interface and do not need to know the intricate details of how the message is physically transmitted or received. This separation ensures that changing the communication hardware or protocol does not impact the core control logic.

## Core `Postman` Interface (`shared_lib/communicate/postman.py`)

The `Postman` base class defines the essential methods for any communication channel:

*   `open_channel()`: Establishes the communication link.
*   `close_channel()`: Terminates the communication link.
*   `send(value)`: Transmits a message (`value` is typically a serialized JSON string).
*   `receive()`: Attempts to read an incoming message.

Subclasses of `Postman` are required to implement the private methods (`_open_channel()`, `_close_channel()`, `_send(value)`, `_receive()`) that provide the concrete, channel-specific logic.

## Concrete Implementations

### `SerialPostman` (`communicate/serial_postman.py`)
*   **Purpose:** This implementation is used exclusively on the **Host computer**. It facilitates communication with physical CircuitPython devices by interacting with standard serial ports (e.g., COM ports on Windows, `/dev/ttyACM*` on Linux).
*   **Technology:** Leverages the `pyserial` library for serial communication.

### `CircuitPythonPostman` (`communicate/circuitpython_postman.py`)
*   **Purpose:** This implementation resides on the **CircuitPython microcontroller**. Its role is to enable the device to send messages back to the Host computer using CircuitPython's native USB CDC (Communications Device Class) data channel.
*   **Technology:** Utilizes the CircuitPython-specific `usb_cdc.data` object, which represents a separate serial stream distinct from the REPL console. This data channel is typically enabled in `boot.py`.

### `DummyPostman` (`communicate/postman.py`)
*   **Purpose:** This is a mock implementation used primarily for **unit testing and offline development**. It simulates sending and receiving messages without requiring any physical hardware or active serial connections.
*   **Functionality:** Can be configured with "canned responses" to mimic device behavior, allowing for isolated testing of Host-side or Device-side logic.

## Message Format Standard

All messages exchanged via any `Postman` implementation **must** adhere to the standardized JSON message structure defined in the [Standard Messaging Protocol](messaging.md). This ensures that messages are unambiguous, machine-readable, and consistently processed by both host and device.

## CircuitPython Compatibility Notes

You will observe `type: ignore` comments within `communicate/postman.py` and `communicate/circuitpython_postman.py`. These are used to inform type checkers (like MyPy) to ignore specific imports or type issues that arise because `usb_cdc` is a module only available in the CircuitPython environment. This allows the host-side Python code to be type-checked without errors, even though it references CircuitPython-specific modules indirectly.