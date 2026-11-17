#!/usr/bin/env python
# -*- coding: utf-8 -*-

import json
from typing import Dict, List
from fastapi import HTTPException, UploadFile
from app.crud.system import UserCRUD, MenuCRUD, DeptCRUD
from app.models.system import OperationLogModel, UserModel
from sqlalchemy import select
from app.core.security import get_password_hash, verify_password
from app.core.exceptions import CustomException
from app.utils.tools import upload_image
from app.schemas.system import (
    Auth,
    UserCreate,
    UserUpdate,
    CurrentUserUpdate,
    CurrentUserPasswordChange,
    UserOut,
    UserSimpleOut,
    UserPermissionOut,
    MenuSimpleOut
)


class UserService:
    """
    用户模块服务层
    """

    @staticmethod
    def record_employee_change(auth: Auth, action: str, user_id: int, **details) -> None:
        auth.session.add(OperationLogModel(
            creator_id=auth.user.id,
            request_method="POST",
            request_path=f"/system/user/{action}",
            request_payload=json.dumps({
                "action": action, "user_id": user_id, "actor": auth.user.username, **details
            }),
            response_code=200,
        ))

    @staticmethod
    async def lock_employee(auth: Auth, user_id: int) -> UserModel:
        user = await auth.session.scalar(
            select(UserModel).where(UserModel.id == user_id).with_for_update(of=UserModel)
        )
        if user is None:
            raise HTTPException(status_code=404, detail="员工不存在")
        return user

    @classmethod
    async def get_detail_by_id(cls, id: int, auth: Auth) -> Dict:
        obj = await UserCRUD(auth).get_by_id(id)
        dept = await DeptCRUD(auth).get(id=obj.dept_id)
        obj.dept_name = dept.name
        return UserSimpleOut.model_validate(obj).model_dump()

    @classmethod
    async def get_detail_by_username(cls, username, auth: Auth) -> UserPermissionOut:
        obj = await UserCRUD(auth).get_by_username(username)
        dept = await DeptCRUD(auth).get(id=obj.dept_id)
        obj.dept_name = dept.name
        return UserPermissionOut.model_validate(obj)

    @classmethod
    async def get_current_user_info(cls, auth: Auth) -> Dict:
        dept = await DeptCRUD(auth).get(id=auth.user.dept_id)
        user_obj = await UserCRUD(auth).get_by_id(auth.user.id)
        data = UserSimpleOut.model_validate(user_obj)
        data.dept_name = dept.name
        data = data.model_dump()

        if auth.user.is_superuser:
            menu_all = await MenuCRUD(auth).get_menu_list(search={'type': ('in', [1, 2]), 'available': True})
            menus = [MenuSimpleOut.model_validate(menu).model_dump() for menu in menu_all]
        else:
            menus = [
                MenuSimpleOut.model_validate(menu).model_dump()
                for role in auth.user.roles
                for menu in role.menus
                if menu.available
             ]

        data["menus"] = menus
        return data

    @classmethod
    async def get_user_list(cls, search: Dict, auth: Auth) -> List[Dict]:
        data = await UserCRUD(auth).get_user_list(search)
        new_data = []
        for obj in data:
            dept = await DeptCRUD(auth).get(id=obj.dept_id)
            obj.dept_name = dept.name
            new_data.append(UserSimpleOut.model_validate(obj).model_dump())

        return new_data

    @classmethod
    async def create_user(cls, user_in: UserCreate, auth: Auth) -> Dict:
        data = await UserCRUD(auth).get_user_list(search={'username': user_in.username})
        if data:
            raise CustomException(msg='已存在相同的账号')

        if user_in.is_superuser:
            raise HTTPException(status_code=400, detail="新建账号必须是员工账号")
        user_in.password = get_password_hash(user_in.password)
        new_user = await UserCRUD(auth).create(
            obj_in=user_in.model_dump(exclude_unset=True, exclude={"role_ids", "position_ids"})
        )
        await UserCRUD(auth).set_user_roles([new_user.id], user_in.role_ids)
        await UserCRUD(auth).set_user_positions([new_user.id], user_in.position_ids)

        cls.record_employee_change(
            auth, "create", new_user.id, available=new_user.available, role_ids=user_in.role_ids
        )
        return UserOut.model_validate(new_user).model_dump()

    @classmethod
    async def update_user(cls, user_in: UserUpdate, auth: Auth) -> Dict:
        user = await cls.lock_employee(auth, user_in.id)
        matches = await UserCRUD(auth).get_user_list(search={"username": user_in.username})
        if any(match.id != user.id for match in matches):
            raise CustomException(msg="已存在相同的用户名")
        if user_in.available is None:
            raise HTTPException(status_code=400, detail="请选择账号状态")
        if user.is_superuser and not user_in.available:
            raise HTTPException(status_code=400, detail="管理员账号不能停用或降级")
        if user_in.is_superuser and not user.is_superuser:
            raise HTTPException(status_code=400, detail="员工账号不能提升为系统管理员")
        old_available = user.available
        old_roles = {role.id for role in user.roles}

        if user_in.password:
            user_in.password = get_password_hash(user_in.password)

        fields = user_in.model_dump(
            exclude_unset=True,
            exclude={"id", "role_ids", "position_ids", "is_superuser", "password"},
        )
        if user_in.password:
            fields["password"] = user_in.password
        new_user = await UserCRUD(auth).update(id=user_in.id, obj_in=fields)
        await UserCRUD(auth).set_user_roles([user_in.id], user_in.role_ids)
        await UserCRUD(auth).set_user_positions([user_in.id], user_in.position_ids)

        if old_available != new_user.available:
            cls.record_employee_change(auth, "enable" if new_user.available else "disable", new_user.id)
        new_roles = {role.id for role in new_user.roles}
        if old_roles != new_roles:
            cls.record_employee_change(auth, "assign-roles", new_user.id, role_ids=sorted(new_roles))

        return UserOut.model_validate(new_user).model_dump()

    @classmethod
    async def update_current_user_info(cls, data: CurrentUserUpdate, auth: Auth) -> Dict:
        new_user = await UserCRUD(auth).update(
            id=auth.user.id,
            obj_in=data.model_dump(exclude_unset=True, exclude={"id"})
        )
        return UserOut.model_validate(new_user).model_dump()

    @classmethod
    async def change_user_password(cls, data: CurrentUserPasswordChange, auth: Auth) -> Dict:
        if not data.old_password or not data.new_password:
            raise CustomException(msg='非法参数')

        user = await UserCRUD(auth).get_by_id(auth.user.id)
        if not verify_password(data.old_password, user.password):
            raise CustomException(msg='原密码输入错误')

        new_password_hash = get_password_hash(data.new_password)
        new_user = await UserCRUD(auth).change_password(user.id, new_password_hash)

        return UserOut.model_validate(new_user).model_dump()

    @classmethod
    async def delete_user(cls, id: int, auth: Auth) -> None:
        user = await cls.lock_employee(auth, id)
        if user.is_superuser:
            raise HTTPException(status_code=400, detail="管理员账号不能删除")
        await UserCRUD(auth).delete(ids=[id])

    @classmethod
    async def set_user_available(cls, ids: List[int], available: bool, auth: Auth) -> None:
        for user_id in sorted(set(ids)):
            user = await cls.lock_employee(auth, user_id)
            if user.is_superuser and not available:
                raise HTTPException(status_code=400, detail="管理员账号不能停用")
            if user.available != available:
                user.available = available
                cls.record_employee_change(auth, "enable" if available else "disable", user_id)

    @classmethod
    async def upload_avatar(cls, file: UploadFile, auth: Auth) -> str:
        avatar = await upload_image(file, dirname='avatar')
        return avatar
