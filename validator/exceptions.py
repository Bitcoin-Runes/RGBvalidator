from typing import Optional, Any, Dict

class ValidatorError(Exception):
    """Base exception class for validator errors"""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)

class UTXOError(ValidatorError):
    """UTXO-related errors"""
    pass

class TokenError(ValidatorError):
    """Token-related errors"""
    pass

class AuthenticationError(ValidatorError):
    """Authentication-related errors"""
    pass

class ValidationError(ValidatorError):
    """Data validation errors"""
    pass

class DatabaseError(ValidatorError):
    """Database-related errors"""
    pass

class SecurityError(ValidatorError):
    """Security-related errors"""
    pass

class MultiSigError(SecurityError):
    """Multi-signature related errors"""
    pass

class TimelockError(SecurityError):
    """Timelock-related errors"""
    pass

class ReplayProtectionError(SecurityError):
    """Transaction replay protection errors"""
    pass

class DoubleSpendingError(SecurityError):
    """Double spending prevention errors"""
    pass

class CacheError(ValidatorError):
    """Cache-related errors"""
    pass

def format_error_response(error: ValidatorError) -> Dict[str, Any]:
    """Format error for API response"""
    return {
        "error": error.__class__.__name__,
        "message": error.message,
        "details": error.details
    }

def handle_validator_error(error: ValidatorError) -> Dict[str, Any]:
    """Handle validator errors and return appropriate response"""
    error_map = {
        UTXOError: {"status_code": 400, "error_type": "UTXO_ERROR"},
        TokenError: {"status_code": 400, "error_type": "TOKEN_ERROR"},
        AuthenticationError: {"status_code": 401, "error_type": "AUTH_ERROR"},
        ValidationError: {"status_code": 422, "error_type": "VALIDATION_ERROR"},
        DatabaseError: {"status_code": 500, "error_type": "DATABASE_ERROR"},
        SecurityError: {"status_code": 403, "error_type": "SECURITY_ERROR"},
        MultiSigError: {"status_code": 400, "error_type": "MULTISIG_ERROR"},
        TimelockError: {"status_code": 400, "error_type": "TIMELOCK_ERROR"},
        ReplayProtectionError: {"status_code": 400, "error_type": "REPLAY_ERROR"},
        DoubleSpendingError: {"status_code": 400, "error_type": "DOUBLE_SPEND_ERROR"},
        CacheError: {"status_code": 500, "error_type": "CACHE_ERROR"}
    }

    error_info = error_map.get(type(error), {"status_code": 500, "error_type": "INTERNAL_ERROR"})
    return {
        "status_code": error_info["status_code"],
        "response": {
            "error_type": error_info["error_type"],
            "message": error.message,
            "details": error.details
        }
    } 