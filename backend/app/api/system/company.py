from typing import Optional

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.dialects.postgresql import insert

from app.core.dependencies import get_current_user
from app.core.exceptions import CustomException
from app.core.router_class import OperationLogRoute
from app.models.company import CompanyProfile
from app.schemas.system import Auth
from app.utils.response import SuccessResponse


router = APIRouter(route_class=OperationLogRoute)


class CompanyProfileInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=200)
    address: Optional[str] = Field(default=None, max_length=500)
    phone: Optional[str] = Field(default=None, max_length=50)


@router.get("/profile", summary="查询公司资料")
async def get_company_profile(auth: Auth = Depends(get_current_user)):
    profile = await auth.session.get(CompanyProfile, 1)
    return SuccessResponse({
        "profile": {
            "name": profile.name,
            "address": profile.address,
            "phone": profile.phone,
        } if profile else None,
        "can_edit": auth.user.is_superuser,
    })


@router.post("/profile/update", summary="更新公司资料")
async def update_company_profile(data: CompanyProfileInput, auth: Auth = Depends(get_current_user)):
    if not auth.user.is_superuser:
        raise CustomException(
            msg="无权限操作",
            code=status.HTTP_403_FORBIDDEN,
            status_code=status.HTTP_403_FORBIDDEN,
        )

    values = data.model_dump()
    values["address"] = values["address"] or None
    values["phone"] = values["phone"] or None
    statement = insert(CompanyProfile).values(id=1, **values)
    await auth.session.execute(statement.on_conflict_do_update(index_elements=[CompanyProfile.id], set_=values))
    return SuccessResponse(values, msg="保存成功")
