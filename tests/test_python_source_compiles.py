import py_compile
import unittest
from pathlib import Path


class PythonSourceCompilationTests(unittest.TestCase):
    def test_repo_python_sources_compile(self):
        repo_root = Path(__file__).resolve().parent.parent
        python_files = [
            path
            for path in repo_root.rglob("*.py")
            if "__pycache__" not in path.parts
        ]

        self.assertTrue(python_files)
        for python_file in python_files:
            with self.subTest(path=str(python_file.relative_to(repo_root))):
                py_compile.compile(str(python_file), doraise=True)


if __name__ == "__main__":
    unittest.main()
