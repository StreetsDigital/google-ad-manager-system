"""
Pytest configuration for reporting tests.
"""
import pytest
import asyncio
from typing import Generator

@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create an event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(autouse=True)
async def setup_teardown():
    """Setup and teardown for each test."""
    # Setup (if needed)
    yield
    # Teardown (if needed) 