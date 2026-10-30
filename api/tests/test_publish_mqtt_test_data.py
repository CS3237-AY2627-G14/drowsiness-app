import argparse
import asyncio
import json

import aiomqtt


def parse_arguments() -> argparse.Namespace:
    argument_parser = argparse.ArgumentParser(
        description="Publish test drowsiness and presence flags to the local broker."
    )
    argument_parser.add_argument("--student", type=int, default=1)
    argument_parser.add_argument("--drowsy", type=int, choices=(0, 1), default=1)
    argument_parser.add_argument("--present", type=int, choices=(0, 1), default=1)
    argument_parser.add_argument("--host", default="127.0.0.1")
    argument_parser.add_argument("--port", type=int, default=1883)
    argument_parser.add_argument("--count", type=int, default=10)
    argument_parser.add_argument("--interval", type=float, default=1.0)
    arguments = argument_parser.parse_args()
    if arguments.student < 1:
        argument_parser.error("--student must be at least 1")
    if not 1 <= arguments.port <= 65535:
        argument_parser.error("--port must be between 1 and 65535")
    if arguments.count < 1:
        argument_parser.error("--count must be at least 1")
    if arguments.interval <= 0:
        argument_parser.error("--interval must be positive")
    return arguments


async def publish_test_reading(arguments: argparse.Namespace) -> None:
    topic = f"wakey/student{arguments.student}/sensors"
    async with aiomqtt.Client(
        hostname=arguments.host,
        port=arguments.port,
    ) as mqtt_client:
        for index in range(arguments.count):
            payload = {
                "drowsy": arguments.drowsy,
                "present": arguments.present,
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
        "check the ESP32 and camera results in the live detection status."
    )


def main() -> None:
    arguments = parse_arguments()
    asyncio.run(publish_test_reading(arguments))


if __name__ == "__main__":
    main()
