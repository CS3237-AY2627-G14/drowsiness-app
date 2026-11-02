import asyncio
import json
import sqlite3
from pathlib import Path
from typing import Any

from modules.calibration.schemas import (
    LabelInterval,
    Recording,
    RecordingDetail,
    TrainingJob,
)
from modules.processing.facade import CameraObservation, StoredSample

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
INSERT OR IGNORE INTO metadata VALUES ('schema_version', '1');
CREATE TABLE IF NOT EXISTS recordings (id TEXT PRIMARY KEY, document TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS samples (
    id INTEGER PRIMARY KEY, recording_id TEXT NOT NULL REFERENCES recordings(id),
    document TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS samples_recording ON samples(recording_id);
CREATE TABLE IF NOT EXISTS labels (
    id INTEGER PRIMARY KEY, recording_id TEXT NOT NULL REFERENCES recordings(id),
    document TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS label_revisions (
    id INTEGER PRIMARY KEY, recording_id TEXT NOT NULL, document TEXT NOT NULL,
    changed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, document TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS snapshots (id TEXT PRIMARY KEY, document TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS observations (
    recording_id TEXT NOT NULL REFERENCES recordings(id), second INTEGER NOT NULL,
    document TEXT NOT NULL, PRIMARY KEY(recording_id, second)
);
"""


def initialize_database(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(directory / "calibration.sqlite3") as database:
        database.executescript(SCHEMA)


class CalibrationRepository:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.path = directory / "calibration.sqlite3"

    def _connect(self) -> sqlite3.Connection:
        database = sqlite3.connect(f"{self.path.as_uri()}?mode=rw", uri=True)
        database.execute("PRAGMA foreign_keys=ON")
        return database

    def is_ready(self) -> bool:
        if not self.path.is_file():
            return False
        try:
            with self._connect() as database:
                version = database.execute(
                    "SELECT value FROM metadata WHERE key='schema_version'"
                ).fetchone()
                return version is not None and version[0] == "1"
        except sqlite3.Error:
            return False

    def _query(self, sql: str, parameters: tuple[Any, ...]) -> list[Any]:
        with self._connect() as database:
            return database.execute(sql, parameters).fetchall()

    async def query(self, sql: str, *parameters: Any) -> list[Any]:
        return await asyncio.to_thread(self._query, sql, parameters)

    async def list_recordings(self) -> list[Recording]:
        rows = await self.query(
            "SELECT r.document, COUNT(s.id) FROM recordings r "
            "LEFT JOIN samples s ON r.id=s.recording_id GROUP BY r.id ORDER BY r.rowid"
        )
        return [
            Recording.model_validate_json(document).model_copy(
                update={"sample_count": count}
            )
            for document, count in rows
        ]

    async def save_recording(self, recording: Recording) -> None:
        await self.query(
            "INSERT INTO recordings VALUES (?, ?) "
            "ON CONFLICT(id) DO UPDATE SET document=excluded.document",
            recording.id,
            recording.model_dump_json(),
        )

    async def add_sample(self, recording_id: str, sample: StoredSample) -> None:
        await self.query(
            "INSERT INTO samples(recording_id, document) VALUES (?, ?)",
            recording_id,
            sample.model_dump_json(),
        )

    def _add_samples(self, recording_id: str, samples: list[StoredSample]) -> None:
        with self._connect() as database:
            database.executemany(
                "INSERT INTO samples(recording_id, document) VALUES (?, ?)",
                [(recording_id, sample.model_dump_json()) for sample in samples],
            )

    async def add_samples(self, recording_id: str, samples: list[StoredSample]) -> None:
        await asyncio.to_thread(self._add_samples, recording_id, samples)

    async def save_snapshot(self, job_id: str, details: list[RecordingDetail]) -> None:
        document = json.dumps(
            [detail.model_dump() for detail in details], sort_keys=True
        )
        await self.query("INSERT INTO snapshots VALUES (?, ?)", job_id, document)

    def _save_observations(
        self, recording_id: str, observations: dict[int, CameraObservation]
    ) -> None:
        with self._connect() as database:
            database.executemany(
                "INSERT INTO observations VALUES (?, ?, ?) "
                "ON CONFLICT(recording_id, second) "
                "DO UPDATE SET document=excluded.document",
                [
                    (recording_id, second, observation.model_dump_json())
                    for second, observation in observations.items()
                ],
            )

    async def save_observations(
        self, recording_id: str, observations: dict[int, CameraObservation]
    ) -> None:
        await asyncio.to_thread(self._save_observations, recording_id, observations)

    async def get_detail(self, recording_id: str) -> RecordingDetail:
        rows = await self.query(
            "SELECT document FROM recordings WHERE id=?", recording_id
        )
        if not rows:
            raise ValueError("Recording not found")
        samples = await self.query(
            "SELECT document FROM samples WHERE recording_id=? ORDER BY id",
            recording_id,
        )
        labels = await self.query(
            "SELECT document FROM labels WHERE recording_id=? ORDER BY id",
            recording_id,
        )
        observations = await self.query(
            "SELECT document FROM observations WHERE recording_id=? ORDER BY second",
            recording_id,
        )
        return RecordingDetail(
            recording=Recording.model_validate_json(rows[0][0]),
            samples=[StoredSample.model_validate_json(row[0]) for row in samples],
            intervals=[LabelInterval.model_validate_json(row[0]) for row in labels],
            observations=[
                CameraObservation.model_validate_json(row[0]) for row in observations
            ],
        )

    def _replace_labels(self, recording_id: str, document: str) -> None:
        with self._connect() as database:
            database.execute(
                "INSERT INTO label_revisions(recording_id, document) VALUES (?, ?)",
                (recording_id, document),
            )
            database.execute("DELETE FROM labels WHERE recording_id=?", (recording_id,))
            database.executemany(
                "INSERT INTO labels(recording_id, document) VALUES (?, ?)",
                [(recording_id, json.dumps(label)) for label in json.loads(document)],
            )

    async def replace_labels(
        self, recording_id: str, intervals: list[LabelInterval]
    ) -> None:
        document = json.dumps([interval.model_dump() for interval in intervals])
        await asyncio.to_thread(self._replace_labels, recording_id, document)

    async def save_job(self, job: TrainingJob) -> None:
        await self.query(
            "INSERT INTO jobs VALUES (?, ?) "
            "ON CONFLICT(id) DO UPDATE SET document=excluded.document",
            job.id,
            job.model_dump_json(),
        )

    async def list_jobs(self) -> list[TrainingJob]:
        rows = await self.query("SELECT document FROM jobs ORDER BY rowid DESC")
        return [TrainingJob.model_validate_json(row[0]) for row in rows]

    async def save_selection(self, model_id: str | None) -> None:
        await self.query(
            "INSERT INTO metadata VALUES ('active_model', ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            model_id or "",
        )

    async def get_selection(self) -> str | None:
        rows = await self.query("SELECT value FROM metadata WHERE key='active_model'")
        return str(rows[0][0]) if rows and rows[0][0] else None
