"""Loaded by pytest before any test module: every test works in a throw-away data dir, never in the real data/
(keys, usage counters and settings there belong to the user)."""
import os
import sys
import tempfile
from pathlib import Path

os.environ["AIIQ_DATA"] = tempfile.mkdtemp(prefix="aiiq-test-data-")
# Mock providers raise network-like errors on purpose: the real connection is not probed (tests set netwatch.probe)
os.environ.setdefault("AIIQ_NETWATCH", "0")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))


def pytest_sessionstart(session):
    from app import config
    real = (Path(__file__).resolve().parents[1] / "data").resolve()
    if Path(config.DATA_DIR).resolve() == real:
        raise SystemExit("tests must not run on the real data/ folder (AIIQ_DATA was not honoured)")
    # Local model servers of this machine are never reached by a test: a test that called the real Ollama loaded a
    # big model on the CPU (a 21.8 GB model with 17 GB free ended in a blue screen). Port 9 (discard) refuses at once.
    config.save_settings({"providers": {"ollama": {"base_url": "http://127.0.0.1:9"},
                                        "lmstudio": {"base_url": "http://127.0.0.1:9/v1"}}})
