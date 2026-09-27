"""Child-process entry: `python -m wall.worker` solves the grid read from stdin.

Each PatternResult is written to stdout as one JSON line so the bot can stream
progress and kill the process at its deadline.
"""

from __future__ import annotations

import base64
import json
import sys

from . import PatternResult, solve_pattern


def encode_result(result: PatternResult) -> str:
    return json.dumps({
        "content": result.content,
        "png": base64.b64encode(result.png).decode("ascii") if result.png else None,
        "retain_image": result.retain_image,
    })


def decode_result(line: bytes) -> PatternResult:
    data = json.loads(line)
    if data.get("error"):
        raise RuntimeError(data["error"])
    png = data.get("png")
    return PatternResult(
        content=data.get("content") or "",
        png=base64.b64decode(png) if png else None,
        retain_image=bool(data.get("retain_image")),
    )


def main() -> int:
    out = sys.stdout
    # Anything the solver prints must not corrupt the JSON stream
    sys.stdout = sys.stderr

    def emit(result: PatternResult) -> None:
        out.write(encode_result(result) + "\n")
        out.flush()

    cleaned = sys.stdin.read().strip()
    try:
        solve_pattern(cleaned, on_update=emit)
    except Exception as error:
        out.write(json.dumps({"error": type(error).__name__}) + "\n")
        out.flush()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
