from datetime import datetime
from typing import Optional

from pydantic import BaseModel, HttpUrl, ConfigDict


# Users
class UserCreate(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    id: int
    username: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# Links
class LinkCreate(BaseModel):
    original_url: HttpUrl
    custom_alias: Optional[str] = None
    expires_at: Optional[datetime] = None


class LinkUpdate(BaseModel):
    original_url: HttpUrl


class LinkResponse(BaseModel):
    short_code: str
    original_url: str
    created_at: datetime
    expires_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class LinkStats(BaseModel):
    short_code: str
    original_url: str
    created_at: datetime
    click_count: int
    last_used_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class LinkHistoryResponse(BaseModel):
    short_code: str
    original_url: str
    created_at: datetime
    deleted_at: datetime
    reason: str
    click_count: int

    model_config = ConfigDict(from_attributes=True)
