import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


@pytest.fixture(scope="session", autouse=True)
def quote_results():
    """Regenerate build/quote-results.ttl so queries over computed results are fresh."""
    import quote
    quote.main(["--ttl", str(ROOT / "build" / "quote-results.ttl")])
