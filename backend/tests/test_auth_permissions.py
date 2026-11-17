from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, Mock, patch

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import AuthPermission, get_current_user
from app.core.exceptions import CustomException
from app.services.system.auth_service import LoginService


class AuthPermissionsTest(IsolatedAsyncioTestCase):
    async def test_existing_access_token_rechecks_role_assignment(self):
        user = SimpleNamespace(id=1, available=True, roles=[], positions=[], is_superuser=False)
        menu = SimpleNamespace(permission="system:user:update", available=True)
        role = SimpleNamespace(available=True, menus=[menu])
        user.roles = [role]
        request = Request({"type": "http"})
        check_permission = AuthPermission(["system:user:update"])

        with (
            patch("app.core.dependencies.decode_jwt_token", return_value=SimpleNamespace(is_refresh=False, sub="staff")),
            patch("app.core.dependencies.UserService.get_detail_by_username", new=AsyncMock(return_value=user)),
        ):
            auth = await get_current_user(request, "existing-token", Mock(spec=AsyncSession))
            await check_permission(request, auth)
            user.roles = []
            auth = await get_current_user(request, "existing-token", Mock(spec=AsyncSession))
            with self.assertRaises(CustomException) as error:
                await check_permission(request, auth)
        self.assertEqual(error.exception.status_code, 403)

    async def test_disabled_user_cannot_use_existing_access_token(self):
        request = Request({"type": "http"})
        with (
            patch("app.core.dependencies.decode_jwt_token", return_value=SimpleNamespace(is_refresh=False, sub="staff")),
            patch("app.core.dependencies.UserService.get_detail_by_username", new=AsyncMock(
                return_value=SimpleNamespace(available=False),
            )),
        ):
            with self.assertRaises(CustomException) as error:
                await get_current_user(request, "existing-token", Mock(spec=AsyncSession))
        self.assertEqual(error.exception.status_code, 401)

    async def test_disabled_user_cannot_refresh_existing_token(self):
        with (
            patch("app.services.system.auth_service.decode_jwt_token", return_value=SimpleNamespace(is_refresh=True, sub="staff")),
            patch("app.services.system.auth_service.UserCRUD.get_by_username", new=AsyncMock(
                return_value=SimpleNamespace(available=False),
            )),
        ):
            with self.assertRaises(CustomException) as error:
                await LoginService.refresh_token("existing-refresh-token", Mock(spec=AsyncSession))
        self.assertEqual(error.exception.status_code, 401)
