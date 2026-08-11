"""Helpers for starting expensive Bokeh sessions without blocking connection setup."""

from __future__ import annotations

import logging
import math
from collections.abc import Callable
from typing import Any


logger = logging.getLogger(__name__)


def schedule_when_client_connected(
    doc: Any,
    callback: Callable[[], None],
    *,
    poll_ms: int = 100,
    max_wait_ms: int = 14_000,
) -> None:
    """Schedule ``callback`` only after the Bokeh WebSocket owns the session.

    A Bokeh HTTP request creates an unused session before the browser opens its
    WebSocket. Running expensive work immediately can block the event loop long
    enough for Bokeh's default 15-second unused-session cleanup to discard that
    session. The WebSocket then creates another session and repeats the work.

    Polling is deliberately lightweight and bounded just below Bokeh's default
    unused-session lifetime. If no browser connects, the unused session is left
    for Bokeh to discard without doing any expensive preparation.
    """
    if poll_ms <= 0:
        raise ValueError("poll_ms must be greater than zero")
    if max_wait_ms < 0:
        raise ValueError("max_wait_ms must not be negative")

    max_attempts = max(1, math.ceil(max_wait_ms / poll_ms))
    attempts = 0

    def _wait_for_connection() -> None:
        nonlocal attempts

        session_context = getattr(doc, "session_context", None)
        if session_context is None:
            doc.add_next_tick_callback(callback)
            return

        session = getattr(session_context, "session", None)
        connection_count = getattr(session, "connection_count", 0) if session is not None else 0
        if connection_count > 0:
            logger.info("Browser connection established; starting dashboard build.")
            doc.add_next_tick_callback(callback)
            return

        attempts += 1
        if attempts >= max_attempts:
            logger.info(
                "No browser connection after %d ms; skipping work for the unused session.",
                max_wait_ms,
            )
            return

        doc.add_timeout_callback(_wait_for_connection, poll_ms)

    doc.add_timeout_callback(_wait_for_connection, 0)
