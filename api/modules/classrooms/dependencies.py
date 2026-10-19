from typing import cast

from fastapi import Request

from modules.classrooms.facade import ClassroomsFacade


def get_classrooms_facade(request: Request) -> ClassroomsFacade:
    return cast(ClassroomsFacade, request.app.state.classrooms_facade)
