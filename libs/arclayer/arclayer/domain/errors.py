class DomainError(Exception):
    """Basis error domain."""


class IllegalTransition(DomainError):
    pass


class InvalidRewardWeights(DomainError):
    pass
