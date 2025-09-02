"""
Otto BGP WebUI Pydantic Schemas
Request/Response validation models
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """Login request body"""
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class SMTPConfig(BaseModel):
    """SMTP configuration for validation"""
    enabled: bool = False
    host: Optional[str] = None
    port: int = Field(default=587, gt=0)
    use_tls: bool = True
    from_address: Optional[str] = None
    to_addresses: List[str] = Field(default_factory=list)
    username: Optional[str] = None
    password: Optional[str] = None

