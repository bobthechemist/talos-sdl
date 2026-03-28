"""
This module serves as the entry point for the shared library. It is responsible for initializing and managing various components that are shared across different modules.
"""

# Import necessary modules and classes from other files within the shared_lib package
from .message_buffer import MessageBuffer, LinearMessageBuffer, CircularMessageBuffer
from .messages import Message, send_problem, send_success
from .statemachine import StateMachine, ContextError, State, StateMachineOrchestrator, StateSequencer
from .utility import check_if_microcontroller

# Add any additional imports or initializations here if needed
