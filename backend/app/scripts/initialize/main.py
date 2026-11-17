from os import environ
from pathlib import Path

import orjson
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import get_password_hash
from app.models import system
from app.models.base import Model
from app.models.company import CompanyProfile


class InitializeData:
    SCRIPT_DIR = Path.joinpath(settings.BASE_DIR, "scripts", "initialize", "data")
    SEED_MODELS = (
        system.DeptModel,
        system.UserModel,
        system.MenuModel,
        system.PositionModel,
        system.RoleModel,
        system.OperationLogModel,
        system.RoleDeptsModel,
        system.RoleMenusModel,
        system.UserPositionsModel,
        system.UserRolesModel,
    )

    def run(self) -> None:
        if not settings.SQL_DB_ENABLE:
            return

        engine = create_engine(settings.SQL_DB_URL.unicode_string().replace("+asyncpg", "", 1))
        try:
            with engine.begin() as connection:
                connection.execute(text("SELECT pg_advisory_xact_lock(39571202)"))
                Model.metadata.create_all(
                    connection,
                    tables=[model.__table__ for model in self.SEED_MODELS] + [CompanyProfile.__table__],
                )

                with Session(bind=connection) as session:
                    if session.scalar(select(system.UserModel.id).limit(1)) is not None:
                        print("数据库已初始化。")
                        return

                    for model in self.SEED_MODELS:
                        records = self._seed_records(model)
                        session.add_all(model(**record) for record in records)
                        session.flush()
                        self._restart_sequence(session, model)
        finally:
            engine.dispose()

        print("数据初始化完成。")

    def _seed_records(self, model) -> list[dict]:
        if model is system.UserModel:
            username = environ.get("ADMIN_USERNAME", "").strip()
            password = environ.get("ADMIN_PASSWORD", "")
            if not username or len(username) > 150:
                raise ValueError("Set ADMIN_USERNAME to a username of 1–150 characters.")
            if len(password) < 12 or len(password.encode("utf-8")) > 72:
                raise ValueError("Set ADMIN_PASSWORD to at least 12 characters and at most 72 UTF-8 bytes.")
            return [{
                "id": 1,
                "username": username,
                "password": get_password_hash(password),
                "name": "系统管理员",
                "dept_id": 1,
                "is_superuser": True,
            }]

        path = self.SCRIPT_DIR / f"{model.__tablename__}.json"
        return orjson.loads(path.read_bytes()) if path.exists() else []

    @staticmethod
    def _restart_sequence(session: Session, model) -> None:
        for column in model.__table__.columns:
            if column.autoincrement is True:
                next_value = (session.scalar(select(func.max(column))) or 0) + 1
                sequence = f"{model.__tablename__}_{column.name}_seq"
                session.execute(text(f"ALTER SEQUENCE {sequence} RESTART WITH {next_value}"))
                break
