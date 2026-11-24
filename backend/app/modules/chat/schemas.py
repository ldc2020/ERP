from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ContactInput(BaseModel):
    user_id: int = Field(gt=0)


class MessageInput(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    client_id: UUID

    @field_validator("content")
    @classmethod
    def nonblank_content(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("消息不能为空")
        return value


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sender_id: int
    content: str
    created_at: datetime
    client_id: UUID
