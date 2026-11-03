"""Tell the launchers whether the web interface needs building or its packages installing.

    python -m siteiq.frontend_build      prints "install", "build" or "fresh"
"""
from __future__ import annotations

from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"
SOURCES = ("src", "index.html", "package.json", "package-lock.json", "vite.config.ts", "tsconfig.json")


def _newest(paths) -> float:
    newest = 0.0
    for path in paths:
        if path.is_dir():
            newest = max([newest] + [p.stat().st_mtime for p in path.rglob("*") if p.is_file()])
        elif path.exists():
            newest = max(newest, path.stat().st_mtime)
    return newest


def status(frontend: Path = FRONTEND) -> str:
    """Packages missing or older than the lockfile: install. Build missing or older than any source: build."""
    modules = frontend / "node_modules" / ".package-lock.json"
    lock = frontend / "package-lock.json"
    if not modules.exists() or (lock.exists() and lock.stat().st_mtime > modules.stat().st_mtime):
        return "install"
    built = frontend / "dist" / "index.html"
    if not built.exists() or _newest(frontend / name for name in SOURCES) > built.stat().st_mtime:
        return "build"
    return "fresh"


if __name__ == "__main__":
    print(status())
