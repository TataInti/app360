class AppException(Exception):
    """Base exception for application errors"""
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.status_code = status_code


class ValidationError(AppException):
    """Raised when validation fails"""
    pass


class NotFoundError(AppException):
    """Raised when resource is not found"""
    def __init__(self, message="Resource not found"):
        super().__init__(message, 404)


class UnauthorizedError(AppException):
    """Raised when access is unauthorized"""
    def __init__(self, message="Unauthorized access"):
        super().__init__(message, 401)


class ForbiddenError(AppException):
    """Raised when access is forbidden"""
    def __init__(self, message="Forbidden"):
        super().__init__(message, 403)