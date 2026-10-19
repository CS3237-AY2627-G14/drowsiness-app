import asyncio

from anyio import CancelScope


async def wait_for_cleanup(cleanup: asyncio.Task[None]) -> None:
    cancellation: asyncio.CancelledError | None = None
    with CancelScope(shield=True):
        while not cleanup.done():
            try:
                await asyncio.shield(cleanup)
            except asyncio.CancelledError as error:
                cancellation = error
        cleanup.result()
    if cancellation is not None:
        raise cancellation
