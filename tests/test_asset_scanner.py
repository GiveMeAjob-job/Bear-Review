import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from asset_scanner import parse_imports, scan_directory, main


def test_parse_imports(tmp_path: Path) -> None:
    file = tmp_path / "example.py"
    file.write_text("import os\nfrom sys import path\n")
    imports = parse_imports(file)
    assert "os" in imports
    assert "sys" in imports


def test_scan_directory(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "mod.py").write_text("import math\n")
    results = scan_directory(tmp_path)
    assert ("a/mod.py", ["math"]) in results


def test_cli_output(tmp_path: Path, capsys) -> None:
    (tmp_path / "m.py").write_text("import json\n")
    main([str(tmp_path)])
    captured = capsys.readouterr().out
    rows = list(csv.reader(captured.strip().splitlines()))
    assert rows[0] == ["file", "imports"]
    assert rows[1][0] == "m.py"
    assert "json" in rows[1][1]
