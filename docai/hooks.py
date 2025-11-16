from __future__ import annotations

import os
import stat
from pathlib import Path

from .util import repo_root

HOOK_BODY = """#!/usr/bin/env sh
# docai pre-commit hook
# Scans repo and updates/generates docs. Aborts commit if docs changed.

if command -v docai >/dev/null 2>&1; then
  DOC_AI="docai"
else
  DOC_AI="python -m docai"
fi

$DOC_AI hook
status=$?
if [ $status -ne 0 ]; then
  echo "\n[docai] Commit aborted. Review and add updated docs before committing."
  exit $status
fi
exit 0
"""


def install_precommit_hook(start: str | Path | None = None) -> Path:
    root = repo_root(Path(start) if start else None)
    hooks = root / ".git" / "hooks"
    hooks.mkdir(parents=True, exist_ok=True)
    hook = hooks / "pre-commit"
    hook.write_text(HOOK_BODY, encoding="utf-8")
    mode = hook.stat().st_mode
    hook.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return hook
