#!/usr/bin/env python
# -*- coding: utf-8 -*-

from typing import Any, Callable, Coroutine
from fastapi import Request, Response
from fastapi.routing import APIRoute
from app.core.database import session_connect
from user_agents import parse
from app.core.config import settings
from app.services.system import LogService
from app.schemas.system import OperationLogCreate, Auth


class OperationLogRoute(APIRoute):
    """
    操作日志装饰器
    """
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        original_route_handler = super().get_route_handler()

        async def custom_route_handler(request: Request) -> Response:
            response: Response = await original_route_handler(request)
            if not settings.OPERATION_LOG_RECORD:
                return response

            route: APIRoute = request.scope.get("route")
            if request.method not in settings.OPERATION_RECORD_METHOD:
                return response
            if route.name in settings.IGNORE_OPERATION_FUNCTION:
                return response

            if not 200 <= response.status_code < 300:
                return response

            user_agent = parse(request.headers.get("user-agent", ""))

            async with session_connect() as session:
                async with session.begin():
                    auth = Auth(session=session)
                    await LogService.create_log(log_in=OperationLogCreate(
                        request_path=request.url.path,
                        request_method=request.method,
                        request_ip=request.client.host if request.client else None,
                        request_os=user_agent.get_os(),
                        request_browser=user_agent.get_browser(),
                        response_code=response.status_code,
                        creator_id=request.scope.get("user_id"),
                    ), auth=auth)

            return response

        return custom_route_handler
