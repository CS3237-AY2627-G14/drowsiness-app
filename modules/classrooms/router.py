from typing import Annotated

from fastapi import APIRouter, Depends

from modules.classrooms.dependencies import get_classrooms_facade
from modules.classrooms.facade import ClassroomInfo, ClassroomsFacade

router = APIRouter(prefix="/api/classrooms", tags=["classrooms"])


@router.get("")
async def list_classrooms(
    classrooms_facade: Annotated[ClassroomsFacade, Depends(get_classrooms_facade)],
) -> list[ClassroomInfo]:
    return await classrooms_facade.list_classrooms()
