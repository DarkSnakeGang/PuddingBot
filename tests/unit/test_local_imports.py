import ast
import importlib
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
LOCAL_PACKAGES = {"chat", "cogs", "wall", "data_management", "github_cache_fetcher",
                  "ce_aggregates", "net_safety"}
SKIP_DIRS = {"native", "tests", ".git", "__pycache__"}


def _local_from_imports():
    for path in ROOT.rglob("*.py"):
        rel = path.relative_to(ROOT)
        if SKIP_DIRS.intersection(rel.parts) or rel.parts[0].startswith((".venv", "_tmp")):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                if node.module.split(".")[0] in LOCAL_PACKAGES:
                    for alias in node.names:
                        yield f"{rel}:{node.lineno}", node.module, alias.name


def test_every_local_from_import_resolves():
    # Includes imports inside functions, which only fail when that code path runs
    missing = []
    for where, module, name in _local_from_imports():
        mod = importlib.import_module(module)
        if name != "*" and not hasattr(mod, name):
            try:
                importlib.import_module(f"{module}.{name}")
            except ImportError:
                missing.append(f"{where}: from {module} import {name}")
    assert not missing, "\n".join(missing)
