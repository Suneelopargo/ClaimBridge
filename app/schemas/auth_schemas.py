from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(
        min_length=1,
        max_length=100,
    )
    password: str = Field(
        min_length=1,
        max_length=200,
    )


class LoginResponse(BaseModel):
    success: bool
    message: str
    accessToken: str
    tokenType: str
    expiresIn: int
    user: dict | None = None
