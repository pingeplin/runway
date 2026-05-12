"""Hidden oracle tests for T03_csv_normalizer.

These exercise the behavioral contract of normalize_csv across the
reader/columns/writer modules. Each test writes its own input file in
a tmp path and asserts on either the normalize_csv return value or the
written output.
"""
from __future__ import annotations

import csv
from pathlib import Path

import pytest

from normalizer import normalize_csv


def _read_output(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        return list(reader)


# --- Header normalization ---------------------------------------------------


def test_snake_case_basic(tmp_path):
    inp = tmp_path / "in.csv"
    out = tmp_path / "out.csv"
    inp.write_text("First Name,Last Name\nAda,Lovelace\n", encoding="utf-8")
    normalize_csv(str(inp), str(out))
    rows = _read_output(out)
    assert rows == [{"first_name": "Ada", "last_name": "Lovelace"}]


def test_snake_case_punctuation_collapse(tmp_path):
    inp = tmp_path / "in.csv"
    out = tmp_path / "out.csv"
    inp.write_text("  E-Mail Address  ,Phone #\na@b.c,555\n", encoding="utf-8")
    normalize_csv(str(inp), str(out))
    rows = _read_output(out)
    assert list(rows[0].keys()) == ["e_mail_address", "phone"]


def test_header_collisions_disambiguated(tmp_path):
    inp = tmp_path / "in.csv"
    out = tmp_path / "out.csv"
    inp.write_text("Name,name,NAME\nx,y,z\n", encoding="utf-8")
    normalize_csv(str(inp), str(out))
    rows = _read_output(out)
    assert list(rows[0].keys()) == ["name", "name_2", "name_3"]


# --- Value normalization ----------------------------------------------------


def test_whitespace_stripped(tmp_path):
    inp = tmp_path / "in.csv"
    out = tmp_path / "out.csv"
    inp.write_text("Name,Age\n  Ada  ,  36  \n", encoding="utf-8")
    normalize_csv(str(inp), str(out))
    rows = _read_output(out)
    assert rows[0]["name"] == "Ada"
    assert rows[0]["age"] == "36"


def test_blank_rows_skipped(tmp_path):
    inp = tmp_path / "in.csv"
    out = tmp_path / "out.csv"
    inp.write_text("A,B\n1,2\n,\n3,4\n", encoding="utf-8")
    normalize_csv(str(inp), str(out))
    rows = _read_output(out)
    assert rows == [{"a": "1", "b": "2"}, {"a": "3", "b": "4"}]


# --- Type inference ---------------------------------------------------------


def test_int_column_inference(tmp_path):
    inp = tmp_path / "in.csv"
    out = tmp_path / "out.csv"
    inp.write_text("count\n1\n2\n3\n", encoding="utf-8")
    summary = normalize_csv(str(inp), str(out))
    # Either reported in the summary or implicitly: integer values round-trip
    # without trailing '.0'. We assert on the file content directly.
    text = out.read_text(encoding="utf-8")
    assert "1\n2\n3" in text


def test_float_column_inference(tmp_path):
    inp = tmp_path / "in.csv"
    out = tmp_path / "out.csv"
    inp.write_text("ratio\n0.5\n1\n2.25\n", encoding="utf-8")
    normalize_csv(str(inp), str(out))
    rows = _read_output(out)
    # All three should be representable as floats.
    for r in rows:
        float(r["ratio"])


def test_mixed_column_stays_string(tmp_path):
    inp = tmp_path / "in.csv"
    out = tmp_path / "out.csv"
    inp.write_text("v\n1\nNA\n3\n", encoding="utf-8")
    normalize_csv(str(inp), str(out))
    rows = _read_output(out)
    assert [r["v"] for r in rows] == ["1", "NA", "3"]


# --- Encoding / line endings -----------------------------------------------


def test_utf8_bom_handled(tmp_path):
    inp = tmp_path / "in.csv"
    out = tmp_path / "out.csv"
    inp.write_bytes("﻿Name,City\nAda,London\n".encode("utf-8"))
    normalize_csv(str(inp), str(out))
    rows = _read_output(out)
    assert rows == [{"name": "Ada", "city": "London"}]


def test_latin1_fallback(tmp_path):
    inp = tmp_path / "in.csv"
    out = tmp_path / "out.csv"
    inp.write_bytes("Name,City\nAda,München\n".encode("latin-1"))
    normalize_csv(str(inp), str(out))
    rows = _read_output(out)
    assert rows[0]["city"].lower().startswith("m")  # round-trips somehow


def test_crlf_input_lf_output(tmp_path):
    inp = tmp_path / "in.csv"
    out = tmp_path / "out.csv"
    inp.write_bytes(b"A,B\r\n1,2\r\n3,4\r\n")
    normalize_csv(str(inp), str(out))
    raw = out.read_bytes()
    assert b"\r\n" not in raw
    assert b"\n" in raw


# --- Cross-module trap: reader & writer both touch columns.py --------------


def test_writer_uses_normalized_headers(tmp_path):
    """Trap: if the agent makes writer.py independent of columns.py's
    header normalization, the output headers will revert to the originals.
    """
    inp = tmp_path / "in.csv"
    out = tmp_path / "out.csv"
    inp.write_text("ALL CAPS,mixed-Case\nx,y\n", encoding="utf-8")
    normalize_csv(str(inp), str(out))
    header_line = out.read_text(encoding="utf-8").splitlines()[0]
    assert "ALL CAPS" not in header_line
    assert "mixed-Case" not in header_line
