"""Generated Bokeh CustomJS callbacks must not dereference a missing namespace.

The callbacks are attached by Bokeh as soon as the document renders, but the
application JavaScript is loaded and wired up later (and can fail part way
through). Guarding only `window.NoiseSurveyApp` and then reaching straight into
`window.NoiseSurveyApp.eventHandlers.handleTap` throws a TypeError inside the
callback instead of logging the intended "not defined" message, so a tap or a
range change during startup produces console noise and swallows the event.
"""

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

SOURCES = [
    REPO_ROOT / 'noise_survey_analysis' / 'ui' / 'components.py',
    REPO_ROOT / 'noise_survey_analysis' / 'visualization' / 'dashBuilder.py',
]

# `window.NoiseSurveyApp && window.NoiseSurveyApp.<namespace>.<member>` — the
# guard stops one level short of the property it goes on to read.
UNGUARDED = re.compile(
    r'window\.NoiseSurveyApp\s*&&\s*(?:typeof\s+)?window\.NoiseSurveyApp\.(\w+)\.(\w+)'
)


class JsCallbackGuardTests(unittest.TestCase):
    def test_generated_callbacks_guard_each_namespace_level(self):
        offenders = []
        for source in SOURCES:
            text = source.read_text(encoding='utf-8')
            for line_number, line in enumerate(text.splitlines(), start=1):
                for namespace, member in UNGUARDED.findall(line):
                    offenders.append(
                        f"{source.relative_to(REPO_ROOT)}:{line_number}: "
                        f"reads .{namespace}.{member} without guarding .{namespace}"
                    )

        self.assertEqual(offenders, [], "\n".join(offenders))


if __name__ == '__main__':
    unittest.main()
