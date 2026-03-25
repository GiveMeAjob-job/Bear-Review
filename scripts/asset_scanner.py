"""Scan Python files and output imports as CSV.

This script walks a directory tree, parses each Python file using
`ast` and writes a CSV to stdout with two columns: `file` and
`imports` (semicolon separated).
"""

from __future__ import annotations

import argparse
import ast
import csv
import sys
from pathlib import Path


def parse_imports(path: Path) -> list[str]:
    """Return a list of imported modules in ``path``."""
    imports: list[str] = []
    with path.open("r", encoding="utf-8") as fh:
        node = ast.parse(fh.read(), filename=str(path))
    for stmt in ast.walk(node):
        if isinstance(stmt, ast.Import):
            for alias in stmt.names:
                imports.append(alias.name)
        elif isinstance(stmt, ast.ImportFrom):
            module = stmt.module or ""
            imports.append(module)
    return imports


def scan_directory(root: Path) -> list[tuple[str, list[str]]]:
    """Scan ``root`` recursively for ``.py`` files."""
    results: list[tuple[str, list[str]]] = []
    for py_file in root.rglob("*.py"):
        imports = parse_imports(py_file)
        rel = py_file.relative_to(root)
        results.append((str(rel), imports))
    return results


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Scan Python imports")
    parser.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="Directory to scan (default: current)",
    )
    args = parser.parse_args(argv)
    root = Path(args.directory)
    records = scan_directory(root)
    writer = csv.writer(sys.stdout)
    writer.writerow(["file", "imports"])
    for file, imports in records:
        writer.writerow([file, ";".join(imports)])


if __name__ == "__main__":
    main()
