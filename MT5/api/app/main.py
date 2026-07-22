"""Compatibility import for the Socket-only MT5 service."""

from app.socket_server import MT5SocketDispatcher, MT5SocketServer, main


__all__ = ["MT5SocketDispatcher", "MT5SocketServer", "main"]
