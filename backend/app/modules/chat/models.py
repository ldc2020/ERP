from sqlalchemy import BIGINT, CheckConstraint, Column, DateTime, ForeignKey, Index, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID

from app.models.base import Model


class ChatConversation(Model):
    __tablename__ = "chat_conversation"
    __table_args__ = (
        CheckConstraint("user_low_id < user_high_id", name="ck_chat_conversation_ordered_users"),
        UniqueConstraint("user_low_id", "user_high_id", name="uq_chat_conversation_users"),
    )

    id = Column(BIGINT, primary_key=True, autoincrement=True)
    user_low_id = Column(BIGINT, ForeignKey("system_user.id", ondelete="CASCADE"), nullable=False, index=True)
    user_high_id = Column(BIGINT, ForeignKey("system_user.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ChatMessage(Model):
    __tablename__ = "chat_message"
    __table_args__ = (
        UniqueConstraint("conversation_id", "sender_id", "client_id", name="uq_chat_message_client"),
        CheckConstraint("char_length(btrim(content)) BETWEEN 1 AND 4000", name="ck_chat_message_content"),
        Index("ix_chat_message_conversation_id_id", "conversation_id", "id"),
    )

    id = Column(BIGINT, primary_key=True, autoincrement=True)
    conversation_id = Column(BIGINT, ForeignKey("chat_conversation.id", ondelete="CASCADE"), nullable=False)
    sender_id = Column(BIGINT, ForeignKey("system_user.id", ondelete="CASCADE"), nullable=False)
    client_id = Column(UUID(as_uuid=True), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
