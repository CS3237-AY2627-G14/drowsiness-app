import re

STUDENT_DATA_TOPIC = "drowsy/stud/{seat_id}/data"
STUDENT_DATA_TOPICS = (
    STUDENT_DATA_TOPIC,
    "drowsy/student{seat_id}/data",
    "wakey/student{seat_id}/sensors",
)
STUDENT_DATA_SUBSCRIPTIONS = (
    "drowsy/stud/+/data",
    "drowsy/+/data",
    "wakey/+/sensors",
)
STUDENT_RESULT_TOPIC = "drowsy/stud/{seat_id}/result"
LECTURER_RESULT_TOPIC = "drowsy/lect/result"
SEAT_PLACEHOLDER = "{seat_id}"
SEAT_ID_GROUP = r"([1-9]\d*)"


def build_student_data_topic(seat_id: int) -> str:
    return STUDENT_DATA_TOPIC.format(seat_id=seat_id)


def build_student_result_topic(seat_id: int) -> str:
    return STUDENT_RESULT_TOPIC.format(seat_id=seat_id)


def build_student_data_subscription() -> str:
    return STUDENT_DATA_TOPIC.format(seat_id="+")


def parse_seat_id(topic: str) -> int | None:
    for topic_pattern in SENSOR_TOPIC_PATTERNS:
        topic_match = topic_pattern.fullmatch(topic)
        if topic_match is not None:
            return int(topic_match.group(1))
    return None


def _build_sensor_topic_pattern(topic_template: str) -> re.Pattern[str]:
    prefix, suffix = topic_template.split(SEAT_PLACEHOLDER)
    escaped_prefix = re.escape(prefix)
    escaped_suffix = re.escape(suffix)
    expression = escaped_prefix + SEAT_ID_GROUP + escaped_suffix
    pattern = re.compile(expression)
    return pattern


SENSOR_TOPIC_PATTERNS = tuple(
    _build_sensor_topic_pattern(topic_template)
    for topic_template in STUDENT_DATA_TOPICS
)
