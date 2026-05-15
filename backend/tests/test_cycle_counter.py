import json
import tempfile
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_export_includes_cycle_counter():
    """export() must write metadata.cycle_counter into the JSON output."""
    from export_data import export
    import sqlite3
    with tempfile.TemporaryDirectory() as d:
        db_path = os.path.join(d, "test.db")
        out_path = os.path.join(d, "api-data.json")
        from storage.db import init_db
        init_db(db_path)
        export(db_path, out_path, cycle_counter=7)
        with open(out_path) as f:
            data = json.load(f)
        assert "metadata" in data, "metadata key missing from export"
        assert data["metadata"]["cycle_counter"] == 7


def test_load_cycle_from_json():
    """_load_cycle_counter() must read metadata.cycle_counter from api-data.json.

    Moved from main.py to core/scrape_orchestrator in #21 so the CLI and
    Flask handler share the same cycle-counter source.
    """
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        json_path = os.path.join(d, "api-data.json")
        with open(json_path, "w") as f:
            json.dump({"metadata": {"cycle_counter": 42}}, f)
        from core import scrape_orchestrator as orch
        original = orch._JSON_OUTPUT_PATH
        orch._JSON_OUTPUT_PATH = Path(json_path)
        try:
            result = orch._load_cycle_counter()
        finally:
            orch._JSON_OUTPUT_PATH = original
        assert result == 43, f"Expected 43 (42+1), got {result}"
