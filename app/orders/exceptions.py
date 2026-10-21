"""Business exceptions for the orders module."""


class OrderError(Exception):
    """Base order exception."""


class OrderNotFoundError(OrderError):
    """Requested order does not exist for the current user."""


class EmptyCartError(OrderError):
    """Checkout was requested for an empty cart."""


class OrderCheckoutError(OrderError):
    """Current cart cannot be converted into an order."""


class InvalidOrderDataError(OrderError):
    """Order domain invariant was violated."""
