import unittest
from unittest.mock import patch

from bokeh.models import ColumnDataSource

from noise_survey_analysis.core.app_callbacks import AppCallbacks


class ImmediateDoc:
    def add_next_tick_callback(self, callback):
        callback()
        return None

    def add_periodic_callback(self, callback, interval):
        return 1

    def remove_periodic_callback(self, callback_id):
        return None

    def get_model_by_name(self, name):
        return None


class ImmediateThread:
    def __init__(self, target=None, args=(), kwargs=None, daemon=None):
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}

    def start(self):
        if self._target:
            self._target(*self._args, **self._kwargs)


class SessionActionBackendTests(unittest.TestCase):
    def test_generate_static_html_session_action_updates_status(self):
        doc = ImmediateDoc()
        audio_control_source = ColumnDataSource(data={'command': [None], 'position_id': [None], 'value': [None]})
        audio_status_source = ColumnDataSource(data={})
        session_action_source = ColumnDataSource(
            data={'command': [None], 'request_id': [None], 'payload': [None]}
        )
        session_status_source = ColumnDataSource(
            data={
                'request_id': [None],
                'level': ['info'],
                'message': [''],
                'output_path': [''],
                'done': [False],
                'updated_at': [0],
            }
        )

        calls = []

        def fake_export_handler(payload=None, request_id=None):
            calls.append((payload, request_id))
            return {
                'success': True,
                'message': 'Export complete',
                'output_path': 'C:/tmp/export.html',
            }

        callbacks = AppCallbacks(
            doc=doc,
            audio_handler=None,
            audio_control_source=audio_control_source,
            audio_status_source=audio_status_source,
            session_action_source=session_action_source,
            session_status_source=session_status_source,
            static_export_request_handler=fake_export_handler,
            streaming_enabled=False,
        )
        callbacks.attach_callbacks()

        with patch('noise_survey_analysis.core.app_callbacks.threading.Thread', ImmediateThread):
            session_action_source.data = {
                'command': ['generate_static_html'],
                'request_id': ['req-1'],
                'payload': [None],
            }

        self.assertEqual(calls, [(None, 'req-1')])
        self.assertEqual(session_action_source.data.get('command'), [None])
        self.assertEqual(session_status_source.data.get('done'), [True])
        self.assertEqual(session_status_source.data.get('level'), ['info'])
        self.assertEqual(session_status_source.data.get('message'), ['Export complete'])
        self.assertEqual(session_status_source.data.get('output_path'), ['C:/tmp/export.html'])


if __name__ == '__main__':
    unittest.main()
