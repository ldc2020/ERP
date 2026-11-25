import json
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from app.api.system import auth


class LoginConfigTest(IsolatedAsyncioTestCase):
    async def test_login_config_exposes_only_captcha_switch(self):
        for enabled in (False, True):
            with self.subTest(enabled=enabled), patch.object(auth.settings, "CAPTCHA_ENABLE", enabled):
                response = await auth.get_login_config()
                self.assertEqual(json.loads(response.body)["data"], {"captcha_enabled": enabled})

    async def test_enabled_captcha_still_blocks_login_without_verification(self):
        from app.core.exceptions import CustomException
        from app.services.system.auth_service import LoginService
        from types import SimpleNamespace

        check = AsyncMock(side_effect=CustomException(msg="验证码不能为空"))
        with patch.object(auth.settings, "CAPTCHA_ENABLE", True), patch(
            "app.services.system.auth_service.CaptchaService.check_captcha", check
        ):
            with self.assertRaises(CustomException):
                await LoginService.authenticate_user(
                    SimpleNamespace(captcha_key="", captcha=""), None, None
                )
        check.assert_awaited_once()
