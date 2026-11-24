from sqlalchemy import case, exists, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import CustomException
from app.models.system import UserModel
from app.modules.chat.models import ChatConversation, ChatMessage
from app.modules.chat.schemas import MessageInput, MessageOut


def _error(message: str, code: int = 400) -> CustomException:
    return CustomException(msg=message, code=code, status_code=code)


def _membership(user_id: int):
    return or_(ChatConversation.user_low_id == user_id, ChatConversation.user_high_id == user_id)


def _message_data(message: ChatMessage) -> dict:
    return MessageOut.model_validate(message).model_dump(mode="json")


class ChatService:
    @staticmethod
    async def search_users(session: AsyncSession, user_id: int, query: str) -> list[dict]:
        query = query.strip()
        if not query:
            return []
        is_contact = exists().where(
            _membership(user_id),
            or_(ChatConversation.user_low_id == UserModel.id, ChatConversation.user_high_id == UserModel.id),
        )
        rows = await session.execute(select(
            UserModel.id, UserModel.username, UserModel.name, UserModel.avatar, is_contact.label("is_contact"),
        ).where(
            UserModel.available.is_(True), UserModel.id != user_id,
            or_(UserModel.username.icontains(query, autoescape=True), UserModel.name.icontains(query, autoescape=True)),
        ).order_by(UserModel.username, UserModel.id).limit(20))
        return [dict(row) for row in rows.mappings()]

    @staticmethod
    async def contacts(session: AsyncSession, user_id: int, conversation_id: int | None = None) -> list[dict]:
        peer_id = case(
            (ChatConversation.user_low_id == user_id, ChatConversation.user_high_id),
            else_=ChatConversation.user_low_id,
        )
        latest_id = select(ChatMessage.id).where(
            ChatMessage.conversation_id == ChatConversation.id,
        ).order_by(ChatMessage.id.desc()).limit(1).correlate(ChatConversation).scalar_subquery()
        statement = select(
            ChatConversation.id, UserModel.id.label("user_id"), UserModel.username,
            UserModel.name, UserModel.avatar, UserModel.available,
            ChatMessage.id.label("message_id"), ChatMessage.sender_id, ChatMessage.content, ChatMessage.created_at,
        ).join(UserModel, UserModel.id == peer_id).outerjoin(ChatMessage, ChatMessage.id == latest_id).where(
            _membership(user_id),
        ).order_by(ChatMessage.id.desc().nulls_last(), ChatConversation.id.desc())
        if conversation_id is not None:
            statement = statement.where(ChatConversation.id == conversation_id)
        rows = await session.execute(statement)
        return [{
            "id": row.id,
            "user": {
                "id": row.user_id, "username": row.username, "name": row.name,
                "avatar": row.avatar, "available": row.available,
            },
            "last_message": {
                "id": row.message_id, "sender_id": row.sender_id, "content": row.content,
                "created_at": row.created_at.isoformat(),
            } if row.message_id is not None else None,
        } for row in rows]

    @staticmethod
    async def create_contact(session: AsyncSession, user_id: int, peer_id: int) -> dict:
        if peer_id == user_id:
            raise _error("不能添加自己为联系人")
        peer = (await session.execute(select(UserModel.id, UserModel.available).where(
            UserModel.id == peer_id,
        ).with_for_update(read=True))).one_or_none()
        if peer is None:
            raise _error("员工不存在", 404)
        if not peer.available:
            raise _error("该员工已停用")
        low, high = sorted((user_id, peer_id))
        statement = insert(ChatConversation).values(user_low_id=low, user_high_id=high)
        await session.execute(statement.on_conflict_do_nothing(constraint="uq_chat_conversation_users"))
        conversation_id = await session.scalar(select(ChatConversation.id).where(
            ChatConversation.user_low_id == low, ChatConversation.user_high_id == high,
        ))
        return (await ChatService.contacts(session, user_id, conversation_id))[0]

    @staticmethod
    async def _conversation(session: AsyncSession, user_id: int, conversation_id: int, lock: bool = False):
        statement = select(ChatConversation).where(ChatConversation.id == conversation_id, _membership(user_id))
        if lock:
            statement = statement.with_for_update()
        conversation = await session.scalar(statement)
        if conversation is None:
            raise _error("会话不存在", 404)
        return conversation

    @staticmethod
    async def messages(
        session: AsyncSession, user_id: int, conversation_id: int,
        before_id: int | None = None, after_id: int | None = None, limit: int = 50,
    ) -> dict:
        await ChatService._conversation(session, user_id, conversation_id)
        if before_id is not None and after_id is not None:
            raise _error("before_id 和 after_id 不能同时使用")
        statement = select(ChatMessage).where(ChatMessage.conversation_id == conversation_id)
        if before_id is not None:
            statement = statement.where(ChatMessage.id < before_id)
        if after_id is not None:
            statement = statement.where(ChatMessage.id > after_id).order_by(ChatMessage.id)
        else:
            statement = statement.order_by(ChatMessage.id.desc())
        messages = list((await session.scalars(statement.limit(limit + 1))).all())
        has_more = len(messages) > limit
        messages = messages[:limit]
        if after_id is None:
            messages.reverse()
        return {"items": [_message_data(message) for message in messages], "has_more": has_more}

    @staticmethod
    async def send_message(session: AsyncSession, user_id: int, conversation_id: int, data: MessageInput) -> dict:
        # Hold this lock through the request transaction: IDs within a conversation
        # become visible in order, so polling after_id cannot skip a late commit.
        conversation = await ChatService._conversation(session, user_id, conversation_id, lock=True)
        existing = await session.scalar(select(ChatMessage).where(
            ChatMessage.conversation_id == conversation_id,
            ChatMessage.sender_id == user_id, ChatMessage.client_id == data.client_id,
        ))
        if existing is not None:
            return _message_data(existing)
        peer_id = conversation.user_high_id if conversation.user_low_id == user_id else conversation.user_low_id
        peer = (await session.execute(select(UserModel.available).where(
            UserModel.id == peer_id,
        ).with_for_update(read=True))).one_or_none()
        if peer is None or not peer.available:
            raise _error("对方账号已停用，无法发送新消息")
        message = ChatMessage(
            conversation_id=conversation_id, sender_id=user_id, client_id=data.client_id, content=data.content,
        )
        session.add(message)
        await session.flush()
        return _message_data(message)
