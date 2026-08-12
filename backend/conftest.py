"""Shared pytest configuration.

Two async styles coexist in this suite: older tests call
`asyncio.get_event_loop().run_until_complete(...)`, newer ones call `asyncio.run(...)`.
On Python 3.12+ the first style raises `RuntimeError: There is no current event loop`
once any test has used `asyncio.run()` — that call closes its loop and leaves no current
one behind. Giving every test a fresh loop keeps both styles working regardless of the
order pytest happens to run them in.
"""
import asyncio

import pytest


@pytest.fixture(autouse=True)
def _fresh_event_loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    try:
        loop.close()
    finally:
        asyncio.set_event_loop(None)
