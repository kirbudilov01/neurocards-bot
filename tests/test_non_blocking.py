
import pytest
import asyncio
import time
from functools import partial

async def run_blocking_isolated(func, *args, **kwargs):
    """
    A copy of the run_blocking function, isolated from the app.db module.
    """
    func_with_args = partial(func, *args, **kwargs)
    return await asyncio.to_thread(func_with_args)

def slow_function():
    """A synchronous function that simulates a blocking I/O call."""
    time.sleep(0.1)
    return "done"

@pytest.mark.asyncio
async def test_run_blocking_isolated_does_not_block():
    start_time = asyncio.get_event_loop().time()

    # Create two tasks that run the slow function
    task1 = asyncio.create_task(run_blocking_isolated(slow_function))
    task2 = asyncio.create_task(run_blocking_isolated(slow_function))

    # Wait for both tasks to complete
    await asyncio.gather(task1, task2)

    end_time = asyncio.get_event_loop().time()

    # If the calls were blocking, the total time would be > 0.2s
    # If they run concurrently, the total time should be ~0.1s
    assert end_time - start_time < 0.15
