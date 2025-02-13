class BubbleViewsException(Exception):
    """Base exception for BubbleViews"""
    pass

class ConfigurationError(BubbleViewsException):
    """Raised when there's an error in configuration"""
    pass

class APIError(BubbleViewsException):
    """Raised when an API call fails"""
    pass

class ValidationError(BubbleViewsException):
    """Raised when content validation fails"""
    pass
