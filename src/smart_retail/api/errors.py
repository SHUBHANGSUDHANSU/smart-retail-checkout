"""Expected API-layer errors mapped centrally to safe HTTP responses."""


class ResourceNotFoundError(LookupError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
