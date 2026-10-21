"""User and authentication domain/application exceptions."""


class UserError(Exception):
    pass


class UserNotFoundError(UserError):
    pass


class EmailAlreadyExistsError(UserError):
    pass


class InvalidUserDataError(UserError):
    pass
