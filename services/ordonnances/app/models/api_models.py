from typing import Optional

from pydantic import BaseModel


class MessageResponse(BaseModel):
    """Standard message response"""

    message: str


class ErrorResponse(BaseModel):
    """Standard error response"""

    error: str
    detail: Optional[str] = None
