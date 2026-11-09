STUDENT_DATA_SUBSCRIPTION = "stud/+/data"
LECTURER_RESULT_TOPIC = "lect/result"


def build_student_data_topic(seat_id: str) -> str:
    return f"stud/{seat_id}/data"


def build_student_result_topic(seat_id: str) -> str:
    return f"stud/{seat_id}/result"
