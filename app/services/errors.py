"""Domain errors. The route layer will translate these to safe HTTP responses."""


class ServiceError(Exception):
    status_code = 400
    code = "service_error"


class AuthenticationRequired(ServiceError):
    status_code = 401
    code = "authentication_required"


class PermissionDenied(ServiceError):
    status_code = 403
    code = "permission_denied"


class NotFound(ServiceError):
    status_code = 404
    code = "not_found"


class Conflict(ServiceError):
    status_code = 409
    code = "conflict"


class InvalidOperation(ServiceError):
    status_code = 422
    code = "invalid_operation"


class DependencyUnavailable(ServiceError):
    status_code = 503
    code = "dependency_unavailable"


class RateLimited(ServiceError):
    status_code = 429
    code = "rate_limited"

    def __init__(self, message: str, retry_after: int):
        super().__init__(message)
        self.retry_after = retry_after
