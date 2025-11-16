from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .scanner import scan_repository
from .docs import update_docs, generate_initial_docs, list_gemini_models
from .hooks import install_precommit_hook
from .util import repo_root, read_json


def _cmd_scan(args) -> int:
    scan_repository()
    print("[docai] Wrote repo_info.json")
    return 0


def _cmd_update_docs(args) -> int:
    root = repo_root()
    before = read_json(root / "repo_info.json") or {}
    scan_repository()
    after = read_json(root / "repo_info.json") or {}
    if before == after:
        print("[docai] Docs already up to date.")
        return 0
    changed = update_docs()
    print("[docai] Updated docs/" + (" (changes)" if changed else " (no changes)"))
    return 0


def _cmd_generate_docs(args) -> int:
    changed = generate_initial_docs()
    if changed:
        print("[docai] Generated initial docs/")
    else:
        print("[docai] docs/ exists or repo_info.json missing; nothing to do")
    return 0


def _cmd_run(args) -> int:
    scan_repository()
    root = repo_root()
    docs_dir = root / "docs"
    if docs_dir.exists():
        changed = update_docs()
        if changed:
            print("[docai] Docs updated; please review changes before committing.")
            return 1
        print("[docai] Docs already up to date.")
        return 0
    else:
        changed = generate_initial_docs()
        if changed:
            print("[docai] Initial docs generated; please review before committing.")
            return 1
        print("[docai] Nothing to do.")
        return 0


def _cmd_install_hook(args) -> int:
    path = install_precommit_hook()
    print(f"[docai] Installed pre-commit hook at {path}")
    return 0


def _cmd_hook(args) -> int:
    # Entry used by the pre-commit hook
    return _cmd_run(args)


def _cmd_parse(args) -> int:
    target = Path(args.path)
    scan_repository(start=target)
    print(f"[docai] Wrote repo_info.json in {repo_root(target)}")
    return 0


def _cmd_generate_initial(args) -> int:
    target = Path(args.path)
    # Ensure repo_info.json exists for target
    scan_repository(start=target)
    changed = generate_initial_docs(start=target)
    if changed:
        print(f"[docai] Generated initial docs/ in {repo_root(target)}")
        return 0
    print("[docai] docs/ exists or repo_info.json missing; nothing to do")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="docai", description="Auto-sync docs with code")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("scan").set_defaults(func=_cmd_scan)
    sub.add_parser("update-docs").set_defaults(func=_cmd_update_docs)
    sub.add_parser("generate-docs").set_defaults(func=_cmd_generate_docs)
    sub.add_parser("run").set_defaults(func=_cmd_run)
    sub.add_parser("install-hook").set_defaults(func=_cmd_install_hook)
    sub.add_parser("hook").set_defaults(func=_cmd_hook)

    p_parse = sub.add_parser("parse", help="Parse a project path and write repo_info.json")
    p_parse.add_argument("path", help="Path to the project root or any child path")
    p_parse.set_defaults(func=_cmd_parse)

    p_gen_init = sub.add_parser("generate-initial", help="Generate initial docs for a project path")
    p_gen_init.add_argument("path", help="Path to the project root or any child path")
    p_gen_init.set_defaults(func=_cmd_generate_initial)

    def _cmd_list_models(_):
        names = list_gemini_models()
        if not names:
            print("[docai] No models found or Gemini not configured. Ensure config.json has gemini_api_key.")
            return 1
        print("[docai] Available Gemini models:")
        for n in names:
            print(f"- {n}")
        return 0

    sub.add_parser("list-models", help="List available Gemini models for the configured API key").set_defaults(func=_cmd_list_models)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    ns = parser.parse_args(argv)
    return ns.func(ns)


if __name__ == "__main__":
    sys.exit(main())
