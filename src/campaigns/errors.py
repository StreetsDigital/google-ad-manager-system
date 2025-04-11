from typing import Dict, Any, Optional

class CampaignError(Exception):
    """Base class for campaign-related errors."""
    pass

class ValidationError(CampaignError):
    """Raised when campaign validation fails."""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        """Initialize validation error.
        
        Args:
            message: Error message describing the validation failure
            details: Optional dictionary containing validation error details
        """
        super().__init__(message)
        self.details = details or {}

class ProcessingError(CampaignError):
    """Raised when campaign processing fails."""
    
    def __init__(self, message: str, response: Optional[Dict[str, Any]] = None) -> None:
        """Initialize processing error.
        
        Args:
            message: Error message describing the processing failure
            response: Optional dictionary containing error response details
        """
        super().__init__(message)
        self.response = response or {} 