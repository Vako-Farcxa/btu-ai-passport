from passport_api.schemas import ErrorCode


class APIError(Exception):
    def __init__(self, status_code: int, code: ErrorCode) -> None:
        self.status_code = status_code
        self.code = code
        super().__init__(code)
