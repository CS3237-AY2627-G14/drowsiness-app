import argparse
import asyncio
import json
import time

import aiomqtt


def parse_arguments() -> argparse.Namespace:
    argument_parser = argparse.ArgumentParser(
        description="Publish one test FSR/ToF reading to the local MQTT broker."
    )
    argument_parser.add_argument("--student", type=int, default=1)
    argument_parser.add_argument("--fsr", type=int, default=1234)
    argument_parser.add_argument("--tof-mm", type=int, default=420)
    argument_parser.add_argument("--host", default="127.0.0.1")
    argument_parser.add_argument("--port", type=int, default=1883)
    argument_parser.add_argument("--count", type=int, default=10)
    argument_parser.add_argument("--interval", type=float, default=1.0)
    arguments = argument_parser.parse_args()
    if arguments.student < 1:
        argument_parser.error("--student must be at least 1")
    if not 0 <= arguments.fsr <= 4095:
        argument_parser.error("--fsr must be between 0 and 4095")
    if arguments.tof_mm < 1:
        argument_parser.error("--tof-mm must be a positive distance in millimeters")
    if not 1 <= arguments.port <= 65535:
        argument_parser.error("--port must be between 1 and 65535")
    if arguments.count < 1:
        argument_parser.error("--count must be at least 1")
    if arguments.interval <= 0:
        argument_parser.error("--interval must be positive")
    return arguments


async def publish_test_reading(arguments: argparse.Namespace) -> None:
    topic = f"drowsy/student{arguments.student}/data"
    async with aiomqtt.Client(
        hostname=arguments.host,
        port=arguments.port,
    ) as mqtt_client:
        for index in range(arguments.count):
            payload = {
                "fsr": arguments.fsr,
                "tof_mm": arguments.tof_mm,
                "timestamp_ms": time.time() * 1000,
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
        "check the FSR and ToF values in the live detection status."
    )


def main() -> None:
    arguments = parse_arguments()
    asyncio.run(publish_test_reading(arguments))


if __name__ == "__main__":
    main()
