class AppError(Exception):
    """Einheitliches Fehlerformat für die API: {"detail": "...", "code": "..."}."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(message)
