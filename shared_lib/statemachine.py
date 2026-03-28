# shared_lib/statemachine.py
#type: ignore
"""
Classes to treat the software-driven laboratory subsystems as state machines

Author(s): BoB LeSuer
"""
from .utility import check_if_microcontroller
from .message_buffer import LinearMessageBuffer # Keep it simple, although at some point, SM should be able to choose
from shared_lib.messages import send_problem, send_success
from time import monotonic

if check_if_microcontroller():
    import adafruit_logging as logging
else:
    import logging

class StateMachine:
    """
    A class to represent a state machine.

    Attributes:
    -----------
    state : State
        The current state of the state machine.
    states : dict
        A dictionary of all states in the state machine.
    flags : dict
        A dictionary of flags used in the state machine.
    running : bool
        Indicates whether the state machine is running.
    is_microcontroller : bool
        Indicates whether the system is a microcontroller.
    init_state : str
        The initial state of the state machine.

    Methods:
    --------
    add_state(state):
        Adds a state to the state machine.
    add_flag(flag, init_value):
        Adds a flag to the state machine.
    go_to_state(state_name):
        Transitions the state machine to the specified state.
    update():
        Updates the current state of the state machine.
    run(state_name=None):
        Starts the state machine.
    stop():
        Stops the state machine.
    """

    def __init__(self, name: str, config: dict, version: str = "0.0.0", init_state: str = 'Initialize', status_callback=None):
        """
        Constructs all the necessary attributes for the state machine object.

        Parameters:
        -----------
        name : str
            The name of the state machine.
        config : dict
            Configuration settings for the state machine.
        version : str, optional
            The version of the state machine (default is '0.0.0').
        init_state : str, optional
            The initial state of the state machine (default is 'Initialize').
        status_callback : callable, optional
            A callback function to build status information (default is None).
        """

        # Read only properties
        self._name = name
        self._version = version
        self._config = config
        self._init_state = init_state
        self._idle_state = 'Idle' # TODO: Replace hardcoded Idle statements with this and allow for modification

        # Mutable properties
        self.state = None
        self.states = {}
        self.flags = {} 
        self.command_handlers = {}
        self.supported_commands = {}
        self.running = False
        self.is_microcontroller = check_if_microcontroller()
        self.sequencer = StateSequencer(self)

        # Populate status info
        self.build_status_info = status_callback if status_callback is not None else lambda m: {}

        # Each state machine has an inbox
        self.inbox = LinearMessageBuffer()
        # TODO: Create a custom handler or other solution to address that adafruit_logging doesn't have basicConfig
        if not self.is_microcontroller:
            logging.basicConfig(level=logging.DEBUG, format='%(asctime)s [%(name)s] %(levelname)s : %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
        self.log = logging.getLogger(self.name)

    # Read only properites
    @property
    def name(self) -> str:
        """
        Returns the name of the state machine.

        Returns:
        --------
        str
            The name of the state machine.
        """
        return self._name
    
    @property
    def version(self) -> str:
        """
        Returns the version of the state machine.

        Returns:
        --------
        str
            The version of the state machine.
        """
        return self._version
    
    @property
    def config(self) -> dict:
        """
        Returns the configuration settings of the state machine.

        Returns:
        --------
        dict
            Configuration settings of the state machine.
        """
        return self._config
    
    @property
    def init_state(self) -> str:
        """
        Returns the initial state of the state machine.

        Returns:
        --------
        str
            The initial state of the state machine.
        """
        return self._init_state
    
    @property
    def idle_state(self) -> str:
        """
        Returns the idle state of the state machine.

        Returns:
        --------
        str
            The idle state of the state machine.
        """
        return self._idle_state

    def add_command(self, name: str, handler, doc: dict):
        """Adds a command handler and its documentation to the machine."""
        self.command_handlers[name] = handler
        self.supported_commands[name] = doc
        
    def handle_instruction(self, payload: dict):
        """
        Dispatches an instruction payload to the correct handler.

        Parameters:
        -----------
        payload : dict
            The instruction payload to be handled.
        """
        # Handler should set any flags and move to a different state
        
        func_name = payload.get("func") if isinstance(payload, dict) else None
        
        handler = self.command_handlers.get(func_name)
        
        if handler:
            # Call the handler, passing the machine instance and payload
            handler(self, payload)
        else:
            self._handle_unknown(payload)
            
    def _handle_unknown(self, payload: dict):
        """
        Default handler for any command not found.

        Parameters:
        -----------
        payload : dict
            The unknown instruction payload.
        """
        func_name = payload.get("func") if payload else "N/A"
        self.log.error(f"Received an unknown instruction: {func_name}")
        send_problem(self, {"message": f"{func_name} is unknown."})

    def add_state(self, state):
        """
        Adds a state to the state machine.

        Parameters:
        -----------
        state : State
            The state to be added.
        
        Raises:
        -------
        ValueError:
            If the state does not define a non-empty 'name' or if there is a duplicate state name.
        """
        if not getattr(state, "name", None):
            raise ValueError(f"State {state.__class__.__name__} must define a non-empty 'name'.")
        if state.name in self.states:
            raise ValueError(f"Duplicate state name: {state.name}")
        self.states[state.name] = state

    def add_flag(self, flag: str, init_value):
        """
        Adds a flag to the state machine.

        Parameters:
        -----------
        flag : str
            The name of the flag.
        init_value : any
            The initial value of the flag.
        """
        self.flags[flag] = init_value

    def go_to_state(self, state_name: str, context=None):
        """
        Transitions the state machine to the specified state.

        Parameters:
        -----------
        state_name : str
            The name of the state to transition to.
        context : dict, optional
            Context data for the new state (default is None).
        
        Raises:
        -------
        Exception:
            If the state machine is not running or if the specified state does not exist.
        """
        if not self.running:
            raise Exception('State machine must be running to do this.')
        if self.state:
            self.state.exit(self)
        
        self.state = self.states.get(state_name)
        if not self.state:
            raise ValueError(f"Attempted to transition to an unknown state: '{state_name}'")
            
        try:
            self.state.enter(self, context=context)
        except ContextError as e:
            self.log.error(f"Aborting sequence. Reason: {e}.")
            if self.sequencer.is_active:
                self.sequencer.abort(e)

    def update(self):
        """
        Updates the current state of the state machine.

        Raises:
        -------
        Exception:
            If the state machine is not running.
        """
        if not self.running:
            raise Exception('State machine must be running to do this.')
        if self.state:
            self.state.update(self)

    def run(self, state_name: str = None):
        """
        Starts the state machine.

        Parameters:
        -----------
        state_name : str, optional
            The name of the state to start with (default is None).
        """
        self.running = True
        if state_name is None:
            self.go_to_state(self._init_state)
        else:
            self.go_to_state(state_name)

    def stop(self):
        """
        Stops the state machine.
        """
        self.running = False

class ContextError(Exception):
    """Error for sequencer"""
    pass

class State:
    """
    A class to represent a state in the state machine.
    """

    def __init__(self):
        """
        Constructs all the necessary attributes for the state object.
        """
        self.entered_at = 0
        self.required_context = []
        self.task_complete = False

    def _validate_context(self, machine: StateMachine, context: dict):
        """
        A private helper called by enter() to ensure the state has what it needs.

        Parameters:
        -----------
        machine : StateMachine
            The state machine instance.
        context : dict
            Context data for the state.
        
        Raises:
        -------
        ContextError:
            If a required context key is missing.
        """
        if machine.sequencer.is_active:
            for key in self.required_context:
                if key not in machine.sequencer.context:
                    raise ContextError(f"State '{self.name}' requires '{key}'.")
 
    @property
    def name(self) -> str:
        """
        Returns the name of the state.

        Returns:
        --------
        str
            The name of the state.
        """
        return ''

    # <<< FIX IS HERE: Signature updated.
    def enter(self, machine: StateMachine, context=None):
        """
        Actions to perform when entering the state.

        Parameters:
        -----------
        machine : StateMachine
            The state machine instance.
        context : dict, optional
            Context data for the new state (default is None).
        """
        self.entered_at = monotonic()
        self.local_context = context or {}
        self._validate_context(machine, self.local_context)
        self.task_complete = False
        machine.log.info(f'{machine.name} entered {self.name} with context={self.local_context}.')

    def exit(self, machine: StateMachine):
        """
        Actions to perform when exiting the state. Override default behavior with custom exit function

        Parameters:
        -----------
        machine : StateMachine
            The state machine instance.
        """
        machine.log.info(f'{machine.name} left {self.name} after {round(monotonic()-self.entered_at,3)} seconds.')

    def update(self, machine: StateMachine):
        """
        Handles advancement logic. Should be called at the end of a state's update function

        Parameters:
        -----------
        machine : StateMachine
            The state machine instance.
        """
        if self.task_complete:
            # Let the sequencer know this state's task is done.
            machine.sequencer.advance()

class StateMachineOrchestrator:
    """
    A class to manage and coordinate multiple state machines.
    
    Attributes:
    -----------
    state_machines : dict
        A dictionary of state machines managed by the orchestrator
    
    Methods:
    --------
    add_state_machine(name, state_machine):
        Adds a state machine to the orchestrator
    remove_state_machine(name):
        Removes a state machine from the orchestrator
    update():
        Updates all state machines managed by the orchestrator
    run_all():
        Starts all state machines managed by the orchestrator
    stop_all():
        Stops all state machines managed by the orchestrator
    """
    def __init__(self):
        """
        Constructs all the necessary attributes for the state machine orchestrator object.
        """
        self.state_machines = {}

    def add_state_machine(self, name: str, state_machine: StateMachine):
        """
        Adds a state machine to the orchestrator.

        Parameters:
        -----------
        name : str
            The name of the state machine.
        state_machine : StateMachine
            The state machine to be added.
        """
        self.state_machines[name] = state_machine

    def remove_state_machine(self, name: str):
        """
        Removes a state machine from the orchestrator.

        Parameters:
        -----------
        name : str
            The name of the state machine to be removed.
        """
        if name in self.state_machines:
            del self.state_machines[name]

    def update(self):
        """
        Updates all state machines managed by the orchestrator.
        """
        for state_machine in self.state_machines.values():
            state_machine.update()

    def run_all(self):
        """
        Starts all state machines managed by the orchestrator.
        """
        for state_machine in self.state_machines.values():
            state_machine.run()

    def stop_all(self):
        """
        Stops all state machines managed by the orchestrator.
        """
        for state_machine in self.state_machines.values():
            state_machine.stop()    

class StateSequencer:
    """
    Manages INSTRUCTION-initiated workflows for a StateMachine
    """
    def __init__(self, machine: StateMachine):
        self.machine = machine
        self.queue = []
        self.context = {}
        self._is_active = False
        self._persistent = False # Default to transient behavior

    @property
    def is_active(self) -> bool:
        """
        Returns whether the sequencer is active.

        Returns:
        --------
        bool
            True if the sequencer is active, False otherwise.
        """
        return self._is_active
    
    def start(self, sequence_list: list, persistent: bool = False, initial_context: dict = None):
        """
        Initiates a workflow

        Parameters:
        -----------
        sequence_list : list
            A list of steps in the sequence.
        persistent : bool, optional
            Whether the sequence should be persistent (default is False).
        initial_context : dict, optional
            Initial context for the sequence (default is None).
        
        Raises:
        -------
        Exception:
            If the sequencer is already active or if the sequence list is empty.
        """
        if self._is_active:
            send_problem(self.machine, "Device is busy with another task.")
            return
        
        if not sequence_list:
            send_problem(self.machine, "Cannot start an empty sequence.")
            return
        
        self.machine.log.info(f"Starting sequence: {sequence_list} -> persistent ='{persistent}'")
        self._is_active = True
        self.queue = sequence_list[:] # Make a copy
        self._persistent = persistent
        self.context = initial_context if initial_context is not None else {}
        self.advance()
    
    def abort(self, reason: str):
        """ Gracefully abort an active sequence. """
        send_problem(self.machine, f"Sequence aborted: {reason}")
        self._reset()
        self.machine.go_to_state(self.machine.idle_state)

    def advance(self):
        """
        Signal that the current state has completed its task.
        Internal method to run the next step or complete the sequence.
        """
        if not self.is_active:
            self.machine.log.debug("advance() called outside of a sequence. Returning to idle state")
            self.machine.go_to_state(self.machine.idle_state)
            return

        if not self.queue:
            self._complete()
            return
        
        step = self.queue.pop(0)
        if not isinstance(step, dict) or "state" not in step:
            self.machine.log.error(f"Invalid step format: {step}")
            self.abort("Invalid sequence step format")
            return
        
        state_name = step["state"]
        self.current_label = step.get("label")
        step_context = step.get("context", {})
        label_info = f" ({self.current_label})" if self.current_label else ""
        
        self.machine.log.info(f"Advancing to {state_name}{label_info} with context = {step_context}")
        self.machine.go_to_state(state_name, context=step_context)
    
    def _complete(self):
        """
        Handles the completion of a sequence
        """
        self.machine.log.info("Sequence complete.")
        sequence_name = self.context.get('name','Unnamed')
        send_success(self.machine, f"Sequence {sequence_name} completed successfully")
        
        was_persistent_sequence = self._persistent
        self._reset()

        if not was_persistent_sequence:
            self.machine.go_to_state(self.machine.idle_state)
    
    def _reset(self):
        """Resets the sequencer to a clean state."""
        self._is_active = False
        self.queue.clear()
        self.context.clear()
        self._persistent = False
