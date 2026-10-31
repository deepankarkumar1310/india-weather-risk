import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def open_meteo_payload():
    return json.loads((FIXTURES / "open_meteo_two_locations.json").read_text(encoding="utf-8"))
