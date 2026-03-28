#type: ignore
import json
import time

class Message():
    """
    Represents a message with subsystem name, status, metadata, and payload.
    
    Args:
        subsystem_name (str, optional): The name of the subsystem that generated the message. Defaults to None.
        status (str, optional): The status level of the message. Must be one of VALID_STATUS. Defaults to None.
        meta (dict, optional): Additional metadata for the message. Defaults to an empty dictionary.
        payload (dict, optional): The main content of the message. Defaults to an empty dictionary.
        timestamp (float, optional): The timestamp when the message was created. Defaults to the current time.
        
    Raises:
        ValueError: If the status is not in VALID_STATUS or if JSON decoding fails.
        TypeError: If meta or payload is not a dictionary.
    """

    VALID_STATUS = {"DEBUG", "TELEMETRY", "INFO", "INSTRUCTION", "SUCCESS", "PROBLEM", "WARNING", "DATA_RESPONSE"}

    def __init__(self, subsystem_name=None, status=None, meta=None, payload=None, timestamp=None):
        """Initializes a Message object."""
        self._subsystem_name = subsystem_name
        # Validate that the status provided to the method is valid
        if status is not None and status not in Message.VALID_STATUS:
           raise ValueError("Invalid Status Level")
        self._status = status
        if meta is None:
            self._meta = {}
        elif not isinstance(meta, dict):
            raise TypeError("meta must be a dictionary")
        else:
            self._meta = meta
        if timestamp is None:
            self._timestamp = time.time()
        else:
            self._timestamp = timestamp
        if payload is None:
            self._payload = {}
        elif not isinstance(payload, dict):
            raise TypeError("payload must be a dictionary")
        else:
            self._payload = payload

    def to_dict(self):
        """Returns a dictionary representation of the message.
        
        Returns:
            dict: A dictionary containing the subsystem_name, status, meta, payload, and timestamp.
        """
        return {
            "subsystem_name": self.subsystem_name,
            "status": self.status,
            "meta": self.meta,
            "payload": self.payload,
            "timestamp": self.timestamp
        }

    def serialize(self):
        """Serializes the message to JSON.
        
        Returns:
            str: A JSON string representation of the message.
        """
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, json_string: str):
        """
        Creates a new Message instance from a JSON string.
        This is a class method.
        
        Args:
            json_string (str): The JSON string to deserialize.
            
        Returns:
            Message: A new Message instance created from the JSON string.
            
        Raises:
            ValueError: If the JSON string is invalid.
        """
        try:
            data = json.loads(json_string)
            subsystem_name = data.get("subsystem_name")
            status = data.get("status")
            meta = data.get("meta", {})
            payload = data.get("payload")
            timestamp = data.get("timestamp")
            # The validation for status is handled by the __init__ method,
            # so we just pass the values along.
            return cls(
                subsystem_name=subsystem_name,
                status=status,
                meta=meta,
                payload=payload,
                timestamp=timestamp
            )
        except json.JSONDecodeError:
            raise ValueError("Invalid JSON string")

    @property
    def subsystem_name(self):
        """Getter for the subsystem_name property.
        
        Returns:
            str: The name of the subsystem that generated the message.
        """
        return self._subsystem_name

    @subsystem_name.setter
    def subsystem_name(self, value):
        """Setter for the subsystem_name property.
        
        Args:
            value (str): The new subsystem name to set.
        """
        self._subsystem_name = value

    @property
    def status(self):
        """Getter for the status property.
        
        Returns:
            str: The status level of the message.
        """
        return self._status
    
    @status.setter
    def status(self, value):
        """Setter for the status property.
        
        Args:
            value (str): The new status to set.
            
        Raises:
            ValueError: If the provided status is not in VALID_STATUS.
        """
        if value not in Message.VALID_STATUS:
            raise ValueError("Invalid Status Level")
        self._status = value

    @property
    def meta(self):
        """Getter for the meta property.
        
        Returns:
            dict: The metadata of the message. Currently returns a fake dictionary.
        """
        # we are ignoring any meta in envelope until this is implemented
        # Should append self._meta to the dict below.
        fake_meta = {
            "id": "fake UUID",
            "seq": -1,
            "origin": "fake UUID"
        }
        return fake_meta

    @meta.setter
    def meta(self, value):
        """Setter for the meta property.
        
        Args:
            value (dict): The new metadata to set.
            
        Raises:
            TypeError: If the provided value is not a dictionary.
        """
        if not isinstance(value, dict):
            raise TypeError("meta must be a dictionary")
        self._meta = value

    @property
    def payload(self):
        """Getter for the payload property.
        
        Returns:
            dict: The main content of the message.
        """
        return self._payload

    @payload.setter
    def payload(self, value):
        """Setter for the payload property.
        
        Args:
            value (dict): The new payload to set.
            
        Raises:
            TypeError: If the provided value is not a dictionary.
        """
        if not isinstance(value, dict):
            raise TypeError("payload must be a dictionary")
        self._payload = value

    @property
    def timestamp(self):
        """Getter for the timestamp property.
        
        Returns:
            float: The timestamp when the message was created.
        """
        return self._timestamp

    @classmethod
    def create_message(cls, subsystem_name=None, status=None, meta=None, payload=None):
        """Creates a Message instance.
        
        Args:
            subsystem_name (str, optional): The name of the subsystem that generated the message. Defaults to None.
            status (str, optional): The status level of the message. Must be one of VALID_STATUS. Defaults to None.
            meta (dict, optional): Additional metadata for the message. Defaults to an empty dictionary.
            payload (dict, optional): The main content of the message. Defaults to an empty dictionary.
            
        Returns:
            Message: A new Message instance created with the provided arguments.
        """
        return cls(subsystem_name=subsystem_name, status=status, meta=meta, payload=payload)

    @classmethod
    def get_valid_status(cls):
        """Returns a set of valid status levels for messages.
        
        Returns:
            set: A set containing all valid status levels.
        """
        return cls.VALID_STATUS

# Make it easy to send properly formatted messages (at least for problem and success at the moment)

def send_problem(machine, msg, error = None):
    """A helper function to create and send a standardized PROBLEM message.
    
    Args:
        machine: The machine object that will log the error and send the message.
        msg (str): The main message describing the problem.
        error (Exception, optional): An exception object associated with the problem. Defaults to None.
        
    Raises:
        AttributeError: If the machine does not have a 'log' or 'postman' attribute.
    """
    machine.log.error(f"msg:{msg}, error:{error}")
    payload = {"message":msg}
    if error is not None:
        payload["exception"] = str(error)
    response = Message.create_message(
        subsystem_name=machine.name,
        status="PROBLEM",
        payload=payload
    )
    machine.postman.send(response.serialize())

def send_success(machine, msg):
    """A helper function to create and send a standardize SUCCESS message.
    
    Args:
        machine: The machine object that will log the success message and send it.
        msg (str): The main message describing the success.
        
    Raises:
        AttributeError: If the machine does not have a 'log' or 'postman' attribute.
    """
    machine.log.info(msg)
    response = Message(
        subsystem_name=machine.name,
        status="SUCCESS",
        payload={"message": msg}
    )
    machine.postman.send(response.serialize())
