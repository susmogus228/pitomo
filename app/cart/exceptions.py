"""Business exceptions for the shopping cart module."""


class CartError(Exception):
    """Base cart exception."""


class CartItemNotFoundError(CartError):
    """Requested cart item does not exist."""


class InsufficientStockError(CartError):
    """Requested cart quantity exceeds current catalog stock."""


class InvalidCartDataError(CartError):
    """Cart domain invariant was violated."""
