"""Tests for terminal endpoints."""
import pytest


def test_terminal_info(client):
    r = client.get("/api/v1/terminal/info")
    assert r.status_code == 200
    data = r.json()
    assert "connected" in data
    assert "trade_allowed" in data
    assert "build" in data
    assert data["name"] == "MetaTrader 5"


def test_terminal_info_connected(client):
    r = client.get("/api/v1/terminal/info")
    assert r.status_code == 200
    assert r.json()["connected"] is True


def test_terminal_info_algo_trading_enabled(client):
    r = client.get("/api/v1/terminal/info")
    assert r.status_code == 200
    assert r.json()["trade_allowed"] is True


def test_account_info(client):
    r = client.get("/api/v1/terminal/account/info")
    assert r.status_code == 200
    data = r.json()
    assert "login" in data
    assert "balance" in data
    assert "equity" in data
    assert "currency" in data
    assert "server" in data


def test_terminal_version(client):
    r = client.get("/api/v1/terminal/version")
    assert r.status_code == 200
