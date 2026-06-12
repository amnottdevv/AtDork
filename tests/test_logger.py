"""
Unit tests for core.logger module.
"""

import logging
import os
from core.logger import setup_logging

def test_setup_logging_console_only(capsys):
    """Should add a console handler without file."""
    root = setup_logging(debug=True, log_file=None)
    # Reset handlers after test to avoid interference
    root.handlers.clear()
    # Just ensure no exception
    logging.info("Test info")
    captured = capsys.readouterr()
    assert "Test info" in captured.out

def test_setup_logging_with_file(tmp_path):
    log_file = tmp_path / "test.log"
    root = setup_logging(debug=True, log_file=str(log_file))
    logging.warning("Warning message")
    root.handlers.clear()
    # Read file
    content = log_file.read_text(encoding="utf-8")
    assert "Warning message" in content

def test_setup_logging_debug_vs_info(capsys):
    root = setup_logging(debug=False, log_file=None)
    logging.debug("Debug message")
    logging.info("Info message")
    root.handlers.clear()
    captured = capsys.readouterr()
    # debug should not appear when console_level is INFO
    assert "Debug message" not in captured.out
    assert "Info message" in captured.out
