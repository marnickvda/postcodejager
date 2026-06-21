import pathlib
import sys

# Ensure the package under src/ is importable even without an editable install.
SRC = pathlib.Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
