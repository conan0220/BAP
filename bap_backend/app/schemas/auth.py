"""Account and token API schemas."""

from pydantic import BaseModel, ConfigDict, Field


class Credentials(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    username: str
    role: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    access_expires_in: int = 1800
    refresh_expires_in: int = 2_592_000


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=32)


class MessageResponse(BaseModel):
    message: str
