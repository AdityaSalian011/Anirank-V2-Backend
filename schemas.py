from pydantic import BaseModel, EmailStr, field_validator
from uuid import UUID
from datetime import datetime


ALLOWED_DOMAINS = {
    "gmail.com", "yahoo.com", "outlook.com"
}

class UserCreate(BaseModel):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def popular_domains_only(cls, value: str) -> str:
        domain = value.lower().split("@")[-1]
        if domain not in ALLOWED_DOMAINS:
            raise ValueError(f"Email domain @{domain} is not supported. Please use one of: {", ".join(sorted(ALLOWED_DOMAINS))}")
        return value.lower()

    password: str


class UserLogin(BaseModel):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def popular_domains_only(cls, value: str) -> str:
        domain = value.lower().split("@")[-1]
        if domain not in ALLOWED_DOMAINS:
            raise ValueError(f"Email domain @{domain} is not supported. Please use one of: {", ".join(sorted(ALLOWED_DOMAINS))}")
        return value.lower()
    
    password: str


class UserOut(BaseModel):
    id: UUID
    email: EmailStr
    created_at: datetime

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str = 'bearer'


class FeedbackRequest(BaseModel):
    mal_id: int
    feedback: int