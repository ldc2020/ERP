import hashlib
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, Mock, patch

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import CustomException
from app.core.security import get_password_hash, verify_password
from app.services.system.auth_service import LoginService


class PasswordCompatibilityTest(IsolatedAsyncioTestCase):
    async def test_legacy_ui_password_is_migrated_after_login(self):
        password = "employee-original-password"
        user = SimpleNamespace(
            id=10, username="employee", available=True,
            password=get_password_hash(hashlib.md5(password.encode()).hexdigest()),
        )
        original_hash = user.password
        session = Mock(spec=AsyncSession)
        session.scalar = AsyncMock(return_value=user.id)
        form = SimpleNamespace(username=user.username, password=password)
        with (
            patch("app.services.system.auth_service.settings.CAPTCHA_ENABLE", False),
            patch("app.services.system.auth_service.UserCRUD.get_by_username", new=AsyncMock(return_value=user)),
            patch("app.services.system.auth_service.UserCRUD.update_last_login", new=AsyncMock(return_value=user)),
        ):
            result = await LoginService.authenticate_user(form, session, Mock())
        self.assertIs(result, user)
        self.assertNotEqual(user.password, original_hash)
        self.assertTrue(verify_password(password, user.password))

    async def test_wrong_password_cannot_migrate_legacy_account(self):
        user = SimpleNamespace(
            id=10, available=True,
            password=get_password_hash(hashlib.md5(b"employee-original-password").hexdigest()),
        )
        original_hash = user.password
        with (
            patch("app.services.system.auth_service.settings.CAPTCHA_ENABLE", False),
            patch("app.services.system.auth_service.UserCRUD.get_by_username", new=AsyncMock(return_value=user)),
        ):
            with self.assertRaises(CustomException):
                await LoginService.authenticate_user(
                    SimpleNamespace(username="employee", password="wrong-password"),
                    Mock(spec=AsyncSession), Mock(),
                )
        self.assertEqual(user.password, original_hash)
