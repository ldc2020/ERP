from fastapi import APIRouter, Depends, Path, Query

from app.core.dependencies import get_current_user
from app.modules.chat.schemas import ContactInput, MessageInput
from app.modules.chat.service import ChatService
from app.schemas.system import Auth
from app.utils.response import SuccessResponse


router = APIRouter(tags=["员工聊天"])


@router.get("/users", summary="搜索聊天员工")
async def search_chat_users(q: str = Query(default="", max_length=150), auth: Auth = Depends(get_current_user)):
    return SuccessResponse(await ChatService.search_users(auth.session, auth.user.id, q))


@router.get("/contacts", summary="查询聊天联系人")
async def list_chat_contacts(auth: Auth = Depends(get_current_user)):
    return SuccessResponse(await ChatService.contacts(auth.session, auth.user.id))


@router.post("/contacts", summary="添加聊天联系人")
async def add_chat_contact(data: ContactInput, auth: Auth = Depends(get_current_user)):
    return SuccessResponse(await ChatService.create_contact(auth.session, auth.user.id, data.user_id))


@router.get("/conversations/{conversation_id}/messages", summary="查询聊天消息")
async def list_chat_messages(
    conversation_id: int = Path(gt=0),
    before_id: int | None = Query(default=None, gt=0),
    after_id: int | None = Query(default=None, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    auth: Auth = Depends(get_current_user),
):
    return SuccessResponse(await ChatService.messages(
        auth.session, auth.user.id, conversation_id, before_id, after_id, limit,
    ))


@router.post("/conversations/{conversation_id}/messages", summary="发送聊天消息")
async def send_chat_message(
    data: MessageInput,
    conversation_id: int = Path(gt=0),
    auth: Auth = Depends(get_current_user),
):
    return SuccessResponse(await ChatService.send_message(auth.session, auth.user.id, conversation_id, data))
