class HTTPError(Exception):
    def __init__(self, status_code: int, message: str, details=None):
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.details = details


def error_payload(code: int, message: str, details=None):
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details,
        }
    }
