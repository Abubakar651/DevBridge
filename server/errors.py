class AppError(Exception):
    """An actionable error safe to return to the browser."""

    def __init__(self, status: int, message: str, code: str = "REQUEST_FAILED", *, validation_hint: str | None = None):
        super().__init__(message)
        self.status = status
        self.message = message
        self.code = code
        self.validation_hint = validation_hint
