#type: ignore

class Postman():
    """
    Base class for message transmission between devices.
    """

    def __init__(self, params: dict):
        """
        Initializes the Postman with a dictionary of parameters.

        Args:
            params: A dictionary containing the configuration parameters.
                   Required Keys: "protocol" (e.g., "serial", "rest", "mqtt")
                   Optional Keys (depending on protocol):
                       "port" (for serial)
                       "baudrate" (for serial, default 115200)
                       "timeout" (for serial, default 1)
                       "url" (for REST)
                       "topic" (for MQTT)
                       ... (other protocol-specific parameters)
        """
        self.params = params
        self.protocol = params.get("protocol")
        if not self.protocol:
            raise ValueError("Protocol must be specified in params")

        self.channel = None
        self.is_open = False

    def open_channel(self):
        """
        Opens the communication channel (implementation-specific).
        """
        if self.is_open:
            return  # Do nothing if already open.  Raise exception?

        self.channel = self._open_channel()
        self.is_open = True

    def close_channel(self):
        """
        Closes the communication channel (implementation-specific).
        """
        if not self.is_open:
            return  # Do nothing if already closed. Raise exception?

        self._close_channel()
        self.channel = None
        self.is_open = False

    def send(self, value):
        """
        Sends a message (implementation-specific).

        Args:
            value: The message to be sent.
        """
        if not self.is_open:
            raise ValueError("Channel is not open.  Must call open_channel() first.")
        self._send(value)

    def receive(self):
        """
        Receives a message (implementation-specific).

        Returns:
            The received message.
        """
        if not self.is_open:
            raise ValueError("Channel is not open.  Must call open_channel() first.")
        return self._receive()

    # Implementation specific

    def _open_channel(self):
        """implementation to open channel"""
        raise NotImplementedError("Implementation specific open not implemented")

    def _close_channel(self):
        """implementation to close channel"""
        raise NotImplementedError("Implementation specific close not implemented")

    def _send(self, value):
        """implementation to send"""
        raise NotImplementedError("Implementation specific send not implemented")

    def _receive(self):
        """implementation to receive"""
        raise NotImplementedError("Implementation specific receive not implemented")
    
#type: ignore

class DummyPostman(Postman):
    """
    Dummy Postman for testing without a real communication channel.  Can be configured
    to send canned responses.
    """

    def __init__(self, params: dict = None, canned_responses=None):
        """
        Initializes the DummyPostman.

        Args:
            params: Dictionary of parameters (ignored, present for compatibility).
            canned_responses: An optional list of values to be returned by 
                              successive calls to receive().  If None, receive() 
                              will always return an empty string.  If a list,
                              receive() will return values from the list in 
                              order, then empty strings once the list is exhausted.
        """
        super().__init__(params or {})  # Pass empty dict if params is None
        self.canned_responses = canned_responses or []
        self.response_index = 0
        self.sent_values = []  # Store sent values for verification

    def _open_channel(self):
        """Dummy open - does nothing."""
        pass  # No real channel to open

    def _close_channel(self):
        """Dummy close - does nothing."""
        pass  # No real channel to close

    def _send(self, value):
        """
        Stores the sent value for later retrieval.

        Args:
            value: The message to be sent.
        """
        self.sent_values.append(value)

    def _receive(self):
        """
        Returns a canned response or an empty string.

        Returns:
            A canned response if available, otherwise an empty string.
        """
        if self.response_index < len(self.canned_responses):
            response = self.canned_responses[self.response_index]
            self.response_index += 1
            return response
        else:
            return ""

    def get_sent_values(self):
        """
        Returns a list of all values sent.

        Returns:
            A list of all sent messages.
        """
        return self.sent_values

    def clear_sent_values(self):
        """Clears the list of sent values."""
        self.sent_values = []
