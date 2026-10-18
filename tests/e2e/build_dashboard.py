"""Build a small real offline dashboard in the local verification copy."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from bokeh.document import Document
from bokeh.embed import file_html
from bokeh.resources import INLINE
from scripts.annotation_benchmark import build_document, generate_fixture, load_manager


def main() -> None:
    output = ROOT / "test-results" / "real-dashboard"
    fixture = output / "survey"
    generate_fixture(fixture, hours=0.4)
    document = Document()
    build_document(document, load_manager(fixture), False)
    (output / "dashboard.html").write_text(
        file_html(document, INLINE, "NSA browser acceptance"), encoding="utf-8")


if __name__ == "__main__":
    main()
