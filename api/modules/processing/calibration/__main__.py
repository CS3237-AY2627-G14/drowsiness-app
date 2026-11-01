import argparse
import asyncio

from core.config import Settings
from modules.processing.calibration.repository import (
    CalibrationRepository,
    initialize_database,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Initialize sensor calibration storage"
    )
    parser.add_argument("command", choices=["init", "reset-selection"])
    arguments = parser.parse_args()
    settings = Settings()
    directory = settings.calibration_directory.resolve()
    if arguments.command == "init":
        initialize_database(directory)
        print(f"Initialized {directory}")
    else:
        repository = CalibrationRepository(directory)
        if not repository.is_ready():
            parser.error("Initialize calibration storage first")
        asyncio.run(repository.save_selection(None))
        print("Restored legacy selection. Restart the API; recordings are unchanged.")


if __name__ == "__main__":
    main()
