import unittest

from noise_survey_analysis.core.session_startup import schedule_when_client_connected


class _FakeSession:
    def __init__(self, connection_count=0):
        self.connection_count = connection_count


class _FakeSessionContext:
    def __init__(self, session=None):
        self.session = session


class _FakeDocument:
    def __init__(self, session_context):
        self.session_context = session_context
        self.timeout_callbacks = []
        self.next_tick_callbacks = []

    def add_timeout_callback(self, callback, timeout_ms):
        self.timeout_callbacks.append((callback, timeout_ms))

    def add_next_tick_callback(self, callback):
        self.next_tick_callbacks.append(callback)

    def run_next_timeout(self):
        callback, timeout_ms = self.timeout_callbacks.pop(0)
        callback()
        return timeout_ms


class SessionStartupTests(unittest.TestCase):
    def test_waits_for_server_session_and_browser_connection(self):
        context = _FakeSessionContext(session=None)
        document = _FakeDocument(context)
        callback = object()

        schedule_when_client_connected(document, callback, poll_ms=100, max_wait_ms=1_000)
        self.assertEqual(document.run_next_timeout(), 0)
        self.assertEqual(document.next_tick_callbacks, [])

        context.session = _FakeSession(connection_count=1)
        self.assertEqual(document.run_next_timeout(), 100)
        self.assertEqual(document.next_tick_callbacks, [callback])

    def test_does_not_build_an_unused_session_after_timeout(self):
        document = _FakeDocument(_FakeSessionContext(_FakeSession(connection_count=0)))

        schedule_when_client_connected(
            document,
            lambda: None,
            poll_ms=100,
            max_wait_ms=200,
        )
        document.run_next_timeout()
        document.run_next_timeout()

        self.assertEqual(document.timeout_callbacks, [])
        self.assertEqual(document.next_tick_callbacks, [])

    def test_non_server_document_runs_on_next_tick(self):
        document = _FakeDocument(session_context=None)
        callback = object()

        schedule_when_client_connected(document, callback)
        document.run_next_timeout()

        self.assertEqual(document.next_tick_callbacks, [callback])

    def test_rejects_invalid_poll_interval(self):
        document = _FakeDocument(session_context=None)
        with self.assertRaises(ValueError):
            schedule_when_client_connected(document, lambda: None, poll_ms=0)


if __name__ == "__main__":
    unittest.main()
