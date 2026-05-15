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
    """load_cycle_counter() must read metadata.cycle_counter from api-data.json."""
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        json_path = os.path.join(d, "api-data.json")
        with open(json_path, "w") as f:
            json.dump({"metadata": {"cycle_counter": 42}}, f)
        # Patch DEFAULT_OUTPUT temporarily
        import main as m
        original = m.JSON_OUTPUT_PATH
        m.JSON_OUTPUT_PATH = json_path
        result = m.load_cycle_counter()
        m.JSON_OUTPUT_PATH = original
        assert result == 43, f"Expected 43 (42+1), got {result}"
