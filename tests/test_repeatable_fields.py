#!/usr/bin/env python3
"""Tests for the shared repeatable configuration-row state helper."""

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("repeatable_fields", ROOT / "repeatable_fields.py")
assert SPEC and SPEC.loader
rows = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rows)


def test_repeatable_rows_add_edit_toggle_and_group():
    state = rows.RepeatableRows()
    index = state.add({"source": "first"})
    state.set_value(index, "env", "USE_FIRST")
    state.toggle(index, "startup")
    state.set_group(index, 3)
    assert state.items == [{"source": "first", "env": "USE_FIRST", "startup": True, "group": 3}]


def test_repeatable_rows_use_one_based_indices_and_ignore_missing_rows():
    state = rows.RepeatableRows([{"source": "first"}])
    assert state.set_value(2, "source", "missing") is False
    assert state.toggle(0, "startup") is False
    assert state.items == [{"source": "first"}]
