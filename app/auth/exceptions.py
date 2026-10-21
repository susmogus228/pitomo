"""Authentication exceptions."""


class AuthenticationError(Exception):
    pass


class InvalidCredentialsError(AuthenticationError):
    pass


class InvalidTokenError(AuthenticationError):
    pass


class AuthenticationRequiredError(AuthenticationError):
    pass


class AuthorizationError(Exception):
    pass
