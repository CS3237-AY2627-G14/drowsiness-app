import argparse
import asyncio
import json
import uuid

import aiomqtt

from modules.processing.mqtt_topics import build_student_data_topic


def parse_arguments() -> argparse.Namespace:
    argument_parser = argparse.ArgumentParser(
        description="Publish raw sensor readings to the local broker."
    )
    argument_parser.add_argument("--student", default="1")
    argument_parser.add_argument("--upper-cm", type=int, default=7)
    argument_parser.add_argument("--lower-mm", type=int, default=150)
    argument_parser.add_argument("--back-raw", type=int, default=1000)
    argument_parser.add_argument("--desk-raw", type=int, default=1500)
    argument_parser.add_argument("--host", default="127.0.0.1")
    argument_parser.add_argument("--port", type=int, default=1883)
    argument_parser.add_argument("--count", type=int, default=10)
    argument_parser.add_argument("--interval", type=float, default=1.0)
    arguments = argument_parser.parse_args()
    if (
        not arguments.student
        or not arguments.student.isascii()
        or not arguments.student.isalnum()
    ):
        argument_parser.error("--student must contain ASCII letters and digits")
    if not 1 <= arguments.port <= 65535:
        argument_parser.error("--port must be between 1 and 65535")
    if arguments.count < 1:
        argument_parser.error("--count must be at least 1")
    if arguments.interval <= 0:
        argument_parser.error("--interval must be positive")
    return arguments


async def publish_test_reading(arguments: argparse.Namespace) -> None:
    topic = build_student_data_topic(arguments.student)
    boot_id = uuid.uuid4().hex
    async with aiomqtt.Client(
        hostname=arguments.host,
        port=arguments.port,
    ) as mqtt_client:
        for index in range(arguments.count):
            payload = {
                "schema_version": 1,
                "boot_id": boot_id,
                "sequence": index,
                "uptime_ms": int(index * arguments.interval * 1000),
                "upper_cm": None if arguments.upper_cm < 0 else arguments.upper_cm,
                "lower_mm": None if arguments.lower_mm < 0 else arguments.lower_mm,
                "back_adc": arguments.back_raw,
                "desk_adc": arguments.desk_raw,
            }
            encoded_payload = json.dumps(payload)
            await mqtt_client.publish(topic, encoded_payload, qos=1)
            print(
                f"Published {index + 1}/{arguments.count} to {topic}: {encoded_payload}"
            )
            if index + 1 < arguments.count:
                await asyncio.sleep(arguments.interval)

    print(
        "With the API and camera stream running for this seat, "
        "check the base sensor and camera results in the live detection status."
    )


def main() -> None:
    arguments = parse_arguments()
    asyncio.run(publish_test_reading(arguments))


if __name__ == "__main__":
    main()
