import json
import os
from pathlib import Path
from typing import Any, Dict

IGNORES = {".git", "venv", ".venv", "__pycache__", "build", "dist"}


def repo_root(start: Path | None = None) -> Path:
    p = Path(start or os.getcwd()).resolve()
    for parent in [p] + list(p.parents):
        if (parent / ".git").exists():
            return parent
    return p


def write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    tmp.replace(path)


def read_json(path: Path) -> Dict[str, Any] | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def iter_python_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        # prune ignored dirs in-place
        dirnames[:] = [d for d in dirnames if d not in IGNORES]
        for name in filenames:
            if name.endswith(".py"):
                yield Path(dirpath) / name
