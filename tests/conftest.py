"""Make `ingest` (src/api) importable and expose common paths to the tests."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API = os.path.join(ROOT, "src", "api")
for p in (API, os.path.dirname(__file__)):
    if p not in sys.path:
        sys.path.insert(0, p)

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
SAMPLE_ESTATE = os.path.join(ROOT, "sample-estate")


def fixture_bytes(name: str) -> bytes:
    with open(os.path.join(FIXTURES, name), "rb") as fh:
        return fh.read()


def sample_bytes(name: str) -> bytes:
    with open(os.path.join(SAMPLE_ESTATE, name), "rb") as fh:
        return fh.read()
