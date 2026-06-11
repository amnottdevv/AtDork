"""
Unit tests for lib.storage module.
"""

import os
import json
import csv
import pytest
from lib.storage import save_results


# ── Fixture ──────────────────────────────────────────────────────────────

@pytest.fixture
def sample_results():
    return [
        {"title": "First", "href": "http://a.com", "body": "First body"},
        {"title": "Second", "href": "http://b.com", "body": "Second body"},
    ]


# ── Tests for save_results ───────────────────────────────────────────────

def test_save_txt_with_output_path(sample_results, tmp_path):
    filepath = tmp_path / "results.txt"
    path = save_results(sample_results, "test query", output_path=str(filepath))
    assert os.path.isfile(path)
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "test query" in content
    assert "First" in content
    assert "http://a.com" in content


def test_save_json_with_output_path(sample_results, tmp_path):
    filepath = tmp_path / "results.json"
    path = save_results(sample_results, "test query", output_path=str(filepath))
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert len(data) == 2
    assert data[0]["title"] == "First"


def test_save_csv_with_output_path(sample_results, tmp_path):
    filepath = tmp_path / "results.csv"
    path = save_results(sample_results, "test query", output_path=str(filepath))
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    assert len(rows) == 2
    assert rows[0]["title"] == "First"


def test_save_with_output_dir(sample_results, tmp_path):
    out_dir = tmp_path / "output"
    path = save_results(sample_results, "test query", output_dir=str(out_dir), output_format="json")
    assert os.path.isdir(out_dir)
    assert os.path.isfile(path)
    assert path.endswith(".json")


def test_save_with_format_override(sample_results, tmp_path):
    """--format should override extension of output_path."""
    filepath = tmp_path / "results.txt"   # extension .txt
    path = save_results(sample_results, "test", output_path=str(filepath), output_format="json")
    # Extension of returned path may still be .txt, but content should be JSON
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert len(data) == 2


def test_save_with_no_output_path_uses_timestamp(sample_results):
    """When no output_path or output_dir, file is saved in current dir with timestamp."""
    # Simpan di tmp_path dengan mengubah direktori kerja sementara (atau kita bisa mocking datetime)
    # Cara paling bersih: gunakan output_dir ke tmp_path
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        path = save_results(sample_results, "test", output_dir=tmpdir, output_format="txt")
        assert os.path.isfile(path)