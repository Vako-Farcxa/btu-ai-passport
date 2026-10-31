from passport_api.schemas import ErrorCode


class APIError(Exception):
    def __init__(
        self, status_code: int, code: ErrorCode, headers: dict[str, str] | None = None
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.headers = headers
        super().__init__(code)


class RateLimitedError(APIError):
    """429 with a Retry-After header (whole seconds)."""

    def __init__(self, retry_after: int) -> None:
        self.retry_after = retry_after
        super().__init__(429, "rate_limited", {"Retry-After": str(retry_after)})
