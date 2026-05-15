"""Root conftest — ensures project root is on sys.path for all tests."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def pytest_configure(config):
    config.addinivalue_line("markers", "scenario: end-to-end scenario tests (require full stack)")
    config.addinivalue_line("markers", "unit: fast unit tests with no external dependencies")
