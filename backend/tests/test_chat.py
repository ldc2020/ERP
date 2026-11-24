"""Real API/PostgreSQL regressions; each run owns a disposable database.

Run with CHAT_TEST_POSTGRES_URL pointing at a PostgreSQL maintenance database.
The suite never creates tables in that database or in the configured ERP database.
"""

import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from unittest import IsolatedAsyncioTestCase, skipUnless
from uuid import uuid4

import psycopg2
from fastapi import FastAPI
from sqlalchemy import insert, update
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import ApiRouter
from app.core.dependencies import session_getter
from app.core.init_app import register_exceptions
from app.core.security import create_jwt_token
from app.models.base import Model
from app.models.system import DeptModel, UserModel
from app.schemas.system import JWTPayload


POSTGRES_URL = os.environ.get("CHAT_TEST_POSTGRES_URL")


@skipUnless(POSTGRES_URL, "Set CHAT_TEST_POSTGRES_URL to run disposable PostgreSQL integration tests")
class ChatApiTest(IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.database_name = f"erp_chat_test_{uuid4().hex}"
        cls.maintenance_url = make_url(POSTGRES_URL).set(drivername="postgresql")
        connection = psycopg2.connect(cls.maintenance_url.render_as_string(hide_password=False))
        try:
            connection.autocommit = True
            with connection.cursor() as cursor:
                cursor.execute(f'CREATE DATABASE "{cls.database_name}"')
        finally:
            connection.close()
        cls.database_url = cls.maintenance_url.set(
            database=cls.database_name, drivername="postgresql+asyncpg",
        ).render_as_string(hide_password=False)

    @classmethod
    def tearDownClass(cls):
        connection = psycopg2.connect(cls.maintenance_url.render_as_string(hide_password=False))
        try:
            connection.autocommit = True
            with connection.cursor() as cursor:
                cursor.execute(f'DROP DATABASE "{cls.database_name}" WITH (FORCE)')
        finally:
            connection.close()

    async def asyncSetUp(self):
        self.engine = create_async_engine(self.database_url)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as connection:
            await connection.run_sync(Model.metadata.drop_all)
            await connection.run_sync(Model.metadata.create_all)
        async with self.sessions.begin() as session:
            await session.execute(insert(DeptModel), [{"id": 1, "name": "Test department"}])
            await session.execute(insert(UserModel), [
                {"id": 1, "username": "alice", "name": "Alice", "password": "private-hash", "available": True, "is_superuser": False, "dept_id": 1},
                {"id": 2, "username": "bob", "name": "鲍勃", "password": "private-hash", "available": True, "is_superuser": False, "dept_id": 1},
                {"id": 3, "username": "admin", "name": "Admin", "password": "private-hash", "available": True, "is_superuser": True, "dept_id": 1},
                {"id": 4, "username": "disabled", "name": "Disabled", "password": "private-hash", "available": False, "is_superuser": False, "dept_id": 1},
            ])
        self.app = FastAPI()
        register_exceptions(self.app)
        self.app.include_router(ApiRouter, prefix="/api")

        async def test_session():
            async with self.sessions() as session:
                async with session.begin():
                    yield session

        self.app.dependency_overrides[session_getter] = test_session

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def request(self, method, path, user="alice", body=None):
        path, _, query = path.partition("?")
        headers = [(b"content-type", b"application/json")]
        if user:
            token = create_jwt_token(JWTPayload(
                sub=user, is_refresh=False, exp=datetime.now(timezone.utc) + timedelta(hours=1),
            ))
            headers.append((b"authorization", f"Bearer {token}".encode()))
        messages = []
        received = False

        async def receive():
            nonlocal received
            if received:
                return {"type": "http.disconnect"}
            received = True
            return {"type": "http.request", "body": json.dumps(body).encode() if body is not None else b""}

        async def send(message):
            messages.append(message)

        await self.app({
            "type": "http", "http_version": "1.1", "method": method,
            "scheme": "http", "path": path, "raw_path": path.encode(),
            "query_string": query.encode(), "headers": headers,
            "client": ("127.0.0.1", 12345), "server": ("test", 80),
        }, receive, send)
        status = next(item["status"] for item in messages if item["type"] == "http.response.start")
        payload = json.loads(b"".join(item.get("body", b"") for item in messages if item["type"] == "http.response.body"))
        return status, payload

    async def create_contact(self, user="alice", target=2):
        status, payload = await self.request("POST", "/api/chat/contacts", user, {"user_id": target})
        self.assertEqual((status, payload["code"]), (200, 200), payload)
        return payload["data"]

    async def send_message(self, conversation, content, user="alice", client_id=None):
        return await self.request("POST", f"/api/chat/conversations/{conversation}/messages", user, {
            "content": content, "client_id": client_id or str(uuid4()),
        })

    async def test_search_is_authenticated_and_does_not_expose_private_user_fields(self):
        status, _ = await self.request("GET", "/api/chat/users?q=bob", user=None)
        self.assertEqual(status, 401)
        status, payload = await self.request("GET", "/api/chat/users?q=%E9%B2%8D")
        self.assertEqual((status, payload["code"]), (200, 200))
        self.assertEqual(len(payload["data"]), 1)
        result = payload["data"][0]
        self.assertEqual(set(result), {"id", "username", "name", "avatar", "is_contact"})
        self.assertEqual((result["id"], result["name"], result["is_contact"]), (2, "鲍勃", False))
        for query in ("", "alice", "disabled", "%25"):
            _, payload = await self.request("GET", f"/api/chat/users?q={query}")
            self.assertEqual(payload["data"], [], query)

    async def test_search_limits_results_and_marks_existing_contacts(self):
        async with self.sessions.begin() as session:
            await session.execute(insert(UserModel), [
                {"id": 10 + i, "username": f"employee{i:02}", "name": "Employee", "password": "secret"}
                for i in range(25)
            ])
        await self.create_contact()
        _, payload = await self.request("GET", "/api/chat/users?q=bob")
        self.assertTrue(payload["data"][0]["is_contact"])
        _, payload = await self.request("GET", "/api/chat/users?q=employee")
        self.assertEqual(len(payload["data"]), 20)

    async def test_contact_is_durable_bidirectional_and_concurrent_adds_are_unique(self):
        contacts = await asyncio.gather(*[
            self.create_contact("alice", 2) if i % 2 == 0 else self.create_contact("bob", 1)
            for i in range(8)
        ])
        self.assertEqual(len({item["id"] for item in contacts}), 1)
        self.assertEqual(set(contacts[0]), {"id", "user", "last_message"})
        self.assertIsNone(contacts[0]["last_message"])
        for user, expected_peer in (("alice", 2), ("bob", 1)):
            _, payload = await self.request("GET", "/api/chat/contacts", user)
            self.assertEqual(len(payload["data"]), 1)
            self.assertEqual(payload["data"][0]["user"]["id"], expected_peer)
            self.assertTrue(payload["data"][0]["user"]["available"])
            self.assertEqual(set(payload["data"][0]["user"]), {"id", "username", "name", "avatar", "available"})
        _, payload = await self.request("GET", "/api/chat/contacts", "admin")
        self.assertEqual(payload["data"], [])

    async def test_self_disabled_and_missing_contacts_are_rejected(self):
        for target in (1, 4, 999999):
            status, payload = await self.request("POST", "/api/chat/contacts", body={"user_id": target})
            self.assertIn(status, (400, 404), payload)
            self.assertNotEqual(payload["code"], 200)
        _, payload = await self.request("GET", "/api/chat/contacts")
        self.assertEqual(payload["data"], [])

    async def test_only_participants_can_read_or_send_even_if_outsider_is_admin(self):
        conversation = (await self.create_contact())["id"]
        await self.send_message(conversation, "private")
        for target in (conversation, 999999):
            for method in ("GET", "POST"):
                status, payload = await self.request(method, f"/api/chat/conversations/{target}/messages", "admin", {
                    "content": "intrusion", "client_id": str(uuid4()),
                } if method == "POST" else None)
                self.assertEqual((status, payload["code"]), (404, 404))

    async def test_message_retry_and_concurrent_sends_are_durable_without_duplicates(self):
        conversation = (await self.create_contact())["id"]
        client_id = str(uuid4())
        responses = await asyncio.gather(*[
            self.send_message(conversation, "你好 <script>alert(1)</script>", client_id=client_id)
            for _ in range(6)
        ])
        self.assertTrue(all(status == 200 and body["code"] == 200 for status, body in responses), responses)
        messages = [body["data"] for _, body in responses]
        self.assertEqual(len({item["id"] for item in messages}), 1)
        self.assertEqual(set(messages[0]), {"id", "sender_id", "content", "created_at", "client_id"})
        self.assertEqual(messages[0]["client_id"], client_id)
        status, same = await self.send_message(conversation, "retry changed text", client_id=client_id)
        self.assertEqual(same["data"], messages[0])
        _, other = await self.send_message(conversation, "Bob reply", "bob", client_id)
        self.assertNotEqual(other["data"]["id"], messages[0]["id"])
        _, history = await self.request("GET", f"/api/chat/conversations/{conversation}/messages", "bob")
        self.assertEqual([item["content"] for item in history["data"]["items"]], ["你好 <script>alert(1)</script>", "Bob reply"])
        _, contacts = await self.request("GET", "/api/chat/contacts")
        self.assertEqual(contacts["data"][0]["last_message"]["content"], "Bob reply")
        self.assertEqual(set(contacts["data"][0]["last_message"]), {"id", "sender_id", "content", "created_at"})

    async def test_message_content_and_client_uuid_are_validated(self):
        conversation = (await self.create_contact())["id"]
        for content in ("", " \n\t ", "x" * 4001):
            _, payload = await self.send_message(conversation, content)
            self.assertEqual(payload["code"], 400)
        _, payload = await self.send_message(conversation, "text", client_id="invalid")
        self.assertEqual(payload["code"], 400)
        _, payload = await self.send_message(conversation, "字" * 4000)
        self.assertEqual(payload["code"], 200)
        _, history = await self.request("GET", f"/api/chat/conversations/{conversation}/messages")
        self.assertEqual(len(history["data"]["items"]), 1)

    async def test_disabled_recipient_rejects_new_messages_but_history_remains_visible(self):
        conversation = (await self.create_contact())["id"]
        _, message = await self.send_message(conversation, "before disable")
        async with self.sessions.begin() as session:
            await session.execute(update(UserModel).where(UserModel.id == 2).values(available=False))
        status, payload = await self.send_message(conversation, "after disable")
        self.assertEqual((status, payload["code"]), (400, 400))
        _, payload = await self.request("GET", "/api/chat/contacts")
        self.assertFalse(payload["data"][0]["user"]["available"])
        _, payload = await self.request("GET", f"/api/chat/conversations/{conversation}/messages")
        self.assertEqual(payload["data"]["items"], [message["data"]])
        status, _ = await self.request("GET", "/api/chat/contacts", "bob")
        self.assertEqual(status, 401)

    async def test_history_pages_latest_older_and_newer_without_skipping(self):
        conversation = (await self.create_contact())["id"]
        messages = []
        for i in range(7):
            _, payload = await self.send_message(conversation, f"message {i}")
            messages.append(payload["data"]["id"])
        path = f"/api/chat/conversations/{conversation}/messages"
        _, payload = await self.request("GET", f"{path}?limit=3")
        self.assertEqual([item["id"] for item in payload["data"]["items"]], messages[4:7])
        self.assertTrue(payload["data"]["has_more"])
        _, payload = await self.request("GET", f"{path}?before_id={messages[4]}&limit=3")
        self.assertEqual([item["id"] for item in payload["data"]["items"]], messages[1:4])
        self.assertTrue(payload["data"]["has_more"])
        _, payload = await self.request("GET", f"{path}?before_id={messages[1]}&limit=3")
        self.assertEqual([item["id"] for item in payload["data"]["items"]], messages[0:1])
        self.assertFalse(payload["data"]["has_more"])
        _, payload = await self.request("GET", f"{path}?after_id={messages[0]}&limit=3")
        self.assertEqual([item["id"] for item in payload["data"]["items"]], messages[1:4])
        self.assertTrue(payload["data"]["has_more"])
        for query in ("before_id=1&after_id=2", "limit=101", "limit=0", "before_id=-1"):
            _, payload = await self.request("GET", f"{path}?{query}")
            self.assertEqual(payload["code"], 400, query)

    async def test_concurrent_send_cannot_publish_a_later_cursor_before_first_commit(self):
        conversation = (await self.create_contact())["id"]
        first_inserted = asyncio.Event()
        release_first = asyncio.Event()
        first_task = None

        async def gated_session():
            async with self.sessions() as session:
                async with session.begin():
                    yield session
                    if asyncio.current_task() is first_task:
                        first_inserted.set()
                        await release_first.wait()

        self.app.dependency_overrides[session_getter] = gated_session
        first_task = asyncio.create_task(self.send_message(conversation, "first"))
        await asyncio.wait_for(first_inserted.wait(), timeout=5)
        second_task = asyncio.create_task(self.send_message(conversation, "second", "bob"))
        try:
            done, _ = await asyncio.wait({second_task}, timeout=0.2)
            self.assertEqual(done, set(), "second send must wait until the first send commits")
        finally:
            release_first.set()
            responses = await asyncio.gather(first_task, second_task)
        first_id, second_id = [payload["data"]["id"] for _, payload in responses]
        self.assertLess(first_id, second_id)
        _, payload = await self.request("GET", f"/api/chat/conversations/{conversation}/messages?after_id={first_id}")
        self.assertEqual([item["content"] for item in payload["data"]["items"]], ["second"])
