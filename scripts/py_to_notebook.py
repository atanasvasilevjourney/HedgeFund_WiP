#!/usr/bin/env python3
"""Convert a .py file into a Jupyter notebook (one cell per top-level def/class + imports block)."""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from textwrap import dedent


def module_docstring(source: str) -> str | None:
    try:
        tree = ast.parse(source)
        if tree.body and isinstance(tree.body[0], ast.Expr) and isinstance(tree.body[0].value, ast.Constant):
            val = tree.body[0].value.value
            if isinstance(val, str):
                return val.strip()
    except SyntaxError:
        pass
    return None


def split_into_chunks(source: str) -> list[tuple[str, str]]:
    """Return list of (title, code) chunks."""
    lines = source.splitlines(keepends=True)
    chunks: list[tuple[str, str]] = []

    # Header: imports + module constants until first def/class
    header: list[str] = []
    i = 0
    if lines and lines[0].startswith('"""'):
        i = 1
        while i < len(lines) and not (lines[i].strip().endswith('"""') and i > 0):
            i += 1
        i += 1

    while i < len(lines):
        stripped = lines[i].lstrip()
        if stripped.startswith("def ") or stripped.startswith("class ") or stripped.startswith("@dataclass"):
            break
        header.append(lines[i])
        i += 1

    if header:
        chunks.append(("Setup & imports", "".join(header).strip() + "\n"))

    current_title = "Code"
    current: list[str] = []

    def flush():
        nonlocal current, current_title
        if current:
            chunks.append((current_title, "".join(current).rstrip() + "\n"))
            current = []

    while i < len(lines):
        line = lines[i]
        stripped = line.lstrip()
        if stripped.startswith("def "):
            flush()
            name = stripped.split("(")[0].replace("def ", "").strip()
            current_title = f"`{name}()`"
            current.append(line)
        elif stripped.startswith("class "):
            flush()
            name = stripped.split("(")[0].replace("class ", "").split(":")[0].strip()
            current_title = f"Class `{name}`"
            current.append(line)
        elif stripped.startswith("@dataclass"):
            flush()
            current_title = "Dataclass"
            current.append(line)
        else:
            current.append(line)
        i += 1

    flush()
    return chunks


def build_notebook(title: str, chunks: list[tuple[str, str]], doc: str | None) -> dict:
    cells = []
    cells.append(
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": [f"# {title}\n\n", *(f"{doc}\n\n" if doc else "")],
        }
    )
    cells.append(
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": [
                "> **Notebook generated from Python source.** "
                "Run cells top-to-bottom. The `.py` module remains the source of truth for the Vercel terminal.\n"
            ],
        }
    )

    for heading, code in chunks:
        cells.append({"cell_type": "markdown", "metadata": {}, "source": [f"## {heading}\n"]})
        cells.append(
            {
                "cell_type": "code",
                "metadata": {},
                "execution_count": None,
                "outputs": [],
                "source": code.splitlines(keepends=True) or ["pass\n"],
            }
        )

    return {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3.11.0"},
        },
        "cells": cells,
    }


def convert_py_to_ipynb(py_path: Path, ipynb_path: Path, title: str | None = None) -> None:
    source = py_path.read_text(encoding="utf-8")
    doc = module_docstring(source)
    chunks = split_into_chunks(source)
    nb = build_notebook(title or py_path.stem.replace("_", " ").title(), chunks, doc)
    ipynb_path.parent.mkdir(parents=True, exist_ok=True)
    ipynb_path.write_text(json.dumps(nb, indent=1), encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("py_file", type=Path)
    p.add_argument("-o", "--output", type=Path, default=None)
    p.add_argument("--title", default=None)
    args = p.parse_args()
    out = args.output or args.py_file.with_suffix(".ipynb")
    convert_py_to_ipynb(args.py_file, out, args.title)
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
