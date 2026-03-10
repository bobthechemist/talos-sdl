#type: ignore
import json
import time

class Message():
    """
    Represents a message with subsystem name, status, metadata, and payload.
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
        """Returns a dictionary representation of the message."""
        return {
            "subsystem_name": self.subsystem_name,
            "status": self.status,
            "meta": self.meta,
            "payload": self.payload,
            "timestamp": self.timestamp
        }

    def serialize(self):
        """Serializes the message to JSON."""
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, json_string: str):
        """
        Creates a new Message instance from a JSON string.
        This is a class method.
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
        return self._subsystem_name

    @subsystem_name.setter
    def subsystem_name(self, value):
        self._subsystem_name = value

    @property
    def status(self):
        return self._status
    
    @status.setter
    def status(self, value):
        if value not in Message.VALID_STATUS:
            raise ValueError("Invalid Status Level")
        self._status = value

    @property
    def meta(self):
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
        if not isinstance(value, dict):
            raise TypeError("meta must be a dictionary")
        self._meta = value

    @property
    def payload(self):
        return self._payload

    @payload.setter
    def payload(self, value):
        if not isinstance(value, dict):
            raise TypeError("payload must be a dictionary")
        self._payload = value

    @property
    def timestamp(self):
        return self._timestamp

    @classmethod
    def create_message(cls, subsystem_name=None, status=None, meta=None, payload=None):
        """Creates a Message instance."""
        return cls(subsystem_name=subsystem_name, status=status, meta=meta, payload=payload)

    @classmethod
    def get_valid_status(cls):
        return cls.VALID_STATUS

# Make it easy to send properly formatted messages (at least for problem and success at the moment)

def send_problem(machine, msg, error = None):
    """A helper function to create and send a standardized PROBLEM message."""
    machine.log.error(f"msg:{msg}, error:{error}")
    payload = {"message":msg}
    if error is not None:
        payload["exception"] = error
    response = Message.create_message(
        subsystem_name=machine.name,
        status="PROBLEM",
        payload=payload
    )
    machine.postman.send(response.serialize())

def send_success(machine, msg):
    """A helper function to create and send a standardize SUCCESS message."""
    machine.log.info(msg)
    response = Message(
        subsystem_name=machine.name,
        status="SUCCESS",
        payload = {"message": msg}
    )
    machine.postman.send(response.serialize())