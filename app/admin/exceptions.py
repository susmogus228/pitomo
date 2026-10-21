"""Administration-specific application exceptions."""


class AdminError(Exception):
    pass


class AdminSelfLockoutError(AdminError):
    pass
