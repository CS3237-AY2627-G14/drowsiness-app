import asyncio

import pytest

from modules.streaming.utils.wait_for_cleanup import wait_for_cleanup


def test_cleanup_task_cancellation_keeps_its_reason() -> None:
    async def run() -> None:
        started = asyncio.Event()
        finish = asyncio.Event()

        async def cleanup() -> None:
            started.set()
            await finish.wait()

        task = asyncio.create_task(cleanup())
        await asyncio.wait_for(started.wait(), 1)
        task.cancel("cleanup stopped")
        with pytest.raises(asyncio.CancelledError, match="cleanup stopped"):
            await wait_for_cleanup(task)

    asyncio.run(run())


def test_already_finished_cleanup_failure_is_propagated() -> None:
    async def run() -> None:
        async def cleanup() -> None:
            raise RuntimeError("cleanup failed")

        task = asyncio.create_task(cleanup())
        await asyncio.wait({task})
        with pytest.raises(RuntimeError, match="cleanup failed"):
            await wait_for_cleanup(task)

    asyncio.run(run())
