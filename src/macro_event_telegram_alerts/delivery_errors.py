"""Secret-safe delivery failures with an explicit retry decision."""


class DeliveryError(RuntimeError):
    """A notification failed and states whether another attempt is appropriate."""

    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable
