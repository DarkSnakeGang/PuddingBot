import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
# UTF-8 emoji/accents that were decoded as cp1252 and re-saved as UTF-8
MOJIBAKE = re.compile("[\u00e2\u00f0][\u0080-\u00bf\u0152-\u0178\u2013-\u203a\u20ac\u2122]|\u00c3[\u0080-\u00bf]")


def test_no_mojibake_in_sources():
    bad = []
    for path in ROOT.rglob("*.py"):
        if any(part in {"native", ".git", "__pycache__"} or part.startswith(".venv") for part in path.parts):
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if MOJIBAKE.search(line) and "MOJIBAKE" not in line:
                bad.append(f"{path.relative_to(ROOT)}:{number}: {line.strip()[:80]}")
    assert not bad, "\n".join(bad)
