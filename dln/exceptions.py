class ExperimentNotStartedError(Exception):
    """Raised when an operation is attempted before starting an experiment."""
    pass

class ExperimentAlreadyStartedError(Exception):
    """Raised when trying to start an experiment while another is active."""
    pass

class ExperimentFinalizedError(Exception):
    """Raised when trying to modify a finalized experiment."""
    pass