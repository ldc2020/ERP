#!/usr/bin/env python
# -*- coding: utf-8 -*-

from fastapi import APIRouter
from .system import SystemRouter
from app.modules.chat.router import router as ChatRouter


ApiRouter = APIRouter()

ApiRouter.include_router(SystemRouter, prefix="/system")
ApiRouter.include_router(ChatRouter, prefix="/chat")
