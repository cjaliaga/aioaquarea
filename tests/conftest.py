"""Test fixtures for aioaquarea tests."""

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def mock_session():
    """Create a mock aiohttp ClientSession."""
    session = MagicMock()
    session.request = AsyncMock()
    session.close = AsyncMock()
    return session


@pytest.fixture
def mock_response():
    """Create a mock aiohttp ClientResponse."""
    resp = MagicMock()
    resp.json = AsyncMock()
    resp.text = AsyncMock()
    resp.status = 200
    resp.content_type = "application/json"
    return resp
