"""
Integration tests for the MT5 API.

These tests run against a live MT5 container. Set environment variables:
  MT5_API_URL  - API base URL (default: http://localhost:8000)
  MT5_API_KEY  - API key for authentication
"""
import os
import pytest
import httpx


BASE_URL = os.getenv("MT5_API_URL", "http://localhost:8000")
API_KEY = os.getenv("MT5_API_KEY", "")


@pytest.fixture(scope="session")
def api_url():
    return BASE_URL


@pytest.fixture(scope="session")
def client():
    headers = {}
    if API_KEY:
        headers["X-API-Key"] = API_KEY
    with httpx.Client(base_url=BASE_URL, headers=headers, timeout=30) as c:
        yield c


@pytest.fixture(scope="session")
def unauth_client():
    with httpx.Client(base_url=BASE_URL, timeout=30) as c:
        yield c
