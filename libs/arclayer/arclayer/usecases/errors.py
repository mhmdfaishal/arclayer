class ApplicationError(Exception):
    pass


class NotFound(ApplicationError):
    pass


class Conflict(ApplicationError):
    pass


class PolicyBusy(ApplicationError):
    """Mode strict sequential: masih ada insiden yang menunggu hasil."""


class FeatureMismatch(ApplicationError):
    """Model embedding atau spesifikasi fitur berbeda dari yang dibekukan di policy."""
