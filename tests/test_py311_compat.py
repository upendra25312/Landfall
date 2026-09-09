"""The `evals` CI runs on **Python 3.11**; local dev may be on 3.12+ where PEP 701
(nested same-quote f-strings, backslashes in f-string expressions) is legal. This
test parses every source file with `feature_version=(3, 11)` so a 3.12-only
construct fails here instead of only in CI collection.

Regression guard for C45 — `scripts/export_all.py` shipped a
`f"{f'…{r['x']}…'}"` in C38 that broke the CI "Unit tests" step (and every eval
gate after it) for six cycles because local dev was on 3.13.
"""
import ast
import os

from conftest import ROOT

_ROOTS = ("scripts", "src", "tests", "evals", "evidence")
_TARGET = (3, 11)


def _py_files():
    for root in _ROOTS:
        for dirpath, _dirs, names in os.walk(os.path.join(ROOT, root)):
            if "__pycache__" in dirpath:
                continue
            for n in names:
                if n.endswith(".py"):
                    yield os.path.join(dirpath, n)


def test_every_source_file_parses_on_python_311():
    offenders = []
    checked = 0
    for path in _py_files():
        checked += 1
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        try:
            ast.parse(src, filename=path, feature_version=_TARGET)
        except SyntaxError as exc:  # noqa: PERF203
            rel = os.path.relpath(path, ROOT)
            offenders.append(f"{rel}:{exc.lineno}: {exc.msg}")
    assert checked > 50, f"only walked {checked} files — path wrong?"
    assert not offenders, "Python 3.11 syntax errors (CI runs 3.11):\n" + "\n".join(offenders)
