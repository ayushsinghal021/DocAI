from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

from .util import repo_root, read_json

try:
    import google.generativeai as genai  # type: ignore
except Exception:  # pragma: no cover
    genai = None  # type: ignore


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)

def _load_bundled_prompts() -> Dict[str, str]:
    # Load prompt templates shipped within this package
    pkg_dir = Path(__file__).resolve().parent
    prompts_dir = pkg_dir / "prompts"
    defaults = {
        "overview": (
            "You are a technical writer. Produce a concise project overview for a Python repository.\n"
            "Use the provided structured repo info (JSON) to describe modules, key classes, and functions.\n"
            "Include a short architecture summary and how to get started.\n"
        ),
        "api": (
            "Generate an API reference in Markdown from the structured repo info (JSON).\n"
            "Group by module. For each class, list methods with one-line summaries. For functions, list signature and summary.\n"
            "Be precise and avoid speculation. If a docstring is missing, keep the generated summary short.\n"
        ),
        "readme": (
            "Draft a README.md for the repository using the structured repo info (JSON).\n"
            "Include: Title, quick start, dependency notes, and a short roadmap. Keep it succinct.\n"
        ),
    }
    contents: Dict[str, str] = {}
    for key, fname in {
        "overview": "overview.txt",
        "api": "api.txt",
        "readme": "readme.txt",
    }.items():
        p = prompts_dir / fname
        try:
            contents[key] = p.read_text(encoding="utf-8")
        except Exception:
            contents[key] = defaults[key]
    return contents


def _render_api_markdown(repo: Dict[str, Any]) -> str:
    lines = ["# API Reference", ""]
    files = repo.get("files", [])
    by_module: Dict[str, Dict[str, Any]] = {f["module"]: f for f in files}
    for mod, info in sorted(by_module.items()):
        lines += [f"## {mod}", ""]
        if info.get("classes"):
            lines += ["### Classes", ""]
            for c in info["classes"]:
                lines += [f"#### {c['name']}", "", c.get("summary", ""), ""]
                methods = c.get("methods", [])
                for m in methods:
                    # args is now list of {name, annotation}
                    arg_list = []
                    for a in (m.get('args') or []):
                        name = a.get('name')
                        ann = a.get('annotation')
                        arg_list.append(f"{name}: {ann}" if ann else f"{name}")
                    sig = f"({', '.join(arg_list)})"
                    ret = m.get('returns')
                    ret_str = f" -> {ret}" if ret else ""
                    lines += [f"- {m['name']}{sig}{ret_str}: {m.get('summary','')}"]
                lines.append("")
        if info.get("functions"):
            lines += ["### Functions", ""]
            for fn in info["functions"]:
                arg_list = []
                for a in (fn.get('args') or []):
                    name = a.get('name')
                    ann = a.get('annotation')
                    arg_list.append(f"{name}: {ann}" if ann else f"{name}")
                sig = f"({', '.join(arg_list)})"
                ret = fn.get('returns')
                ret_str = f" -> {ret}" if ret else ""
                lines += [f"- {fn['name']}{sig}{ret_str}: {fn.get('summary','')}"]
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def update_docs(start: str | Path | None = None) -> bool:
    """Update docs using repo_info.json. Returns True if files changed."""
    root = repo_root(Path(start) if start else None)
    repo = read_json(root / "repo_info.json")
    if not repo:
        return False
    docs = root / "docs"
    _ensure_dir(docs)

    model = _gemini_client()
    prompts = _load_bundled_prompts()

    # Compute new contents
    api_md_det = _render_api_markdown(repo)
    overview_md = "# Overview\n\n" + (repo.get("files") and "Auto-generated overview." or "") + "\n"
    readme_md = "# README\n\nProject README.\n"

    if model:
        print("[docai] Updating docs with Gemini...")
        over = _call_gemini(model, prompts.get("overview", ""), repo)
        if over.strip():
            overview_md = over
        rd = _call_gemini(model, prompts.get("readme", ""), repo)
        if rd.strip():
            readme_md = rd
        api_g = _call_gemini(model, prompts.get("api", ""), repo)
        api_md = api_g if api_g.strip() else api_md_det
    else:
        api_md = api_md_det

    # Existing files content
    paths = {
        "overview": docs / "overview.md",
        "readme": docs / "readme.md",
        "api": docs / "api_reference.md",
    }
    before_over = paths["overview"].read_text(encoding="utf-8") if paths["overview"].exists() else None
    before_readme = paths["readme"].read_text(encoding="utf-8") if paths["readme"].exists() else None
    before_api = paths["api"].read_text(encoding="utf-8") if paths["api"].exists() else None

    _write_text(paths["overview"], overview_md)
    _write_text(paths["readme"], readme_md)
    _write_text(paths["api"], api_md)

    changed = (before_over != overview_md) or (before_readme != readme_md) or (before_api != api_md)
    return changed


def _gemini_client():
    if genai is None:
        return None
    # Only read API key from this package's root config.json
    pkg_root = Path(__file__).resolve().parents[1]
    api_key = None
    model_name = None
    try:
        cfg = read_json(pkg_root / "config.json")
        if isinstance(cfg, dict):
            api_key = cfg.get("gemini_api_key") or cfg.get("GOOGLE_API_KEY")
            model_name = cfg.get("gemini_model")
    except Exception:
        api_key = None
        model_name = None
    if not api_key:
        return None
    genai.configure(api_key=api_key)
    try:
        name = (model_name).strip()
        print(f"[docai] Using Gemini model: {name}")
        return genai.GenerativeModel(name)
    except Exception:
        return None


def _call_gemini(model, prompt: str, json_payload: Dict[str, Any]) -> str:
    try:
        parts = [prompt, "\n\nJSON:\n", str(json_payload)]
        resp = model.generate_content(parts)  # type: ignore
        text = getattr(resp, "text", None)
        if not text and hasattr(resp, "candidates") and resp.candidates:
            text = resp.candidates[0].content.parts[0].text  # type: ignore
        return text or ""
    except Exception as e:
        msg = str(e)
        print(f"[docai] Gemini error: {msg}")
        return ""


def list_gemini_models() -> list[str]:
    if genai is None:
        return []
    # Use package root config for API key
    pkg_root = Path(__file__).resolve().parents[1]
    cfg = read_json(pkg_root / "config.json") or {}
    api_key = cfg.get("gemini_api_key") or cfg.get("GOOGLE_API_KEY")
    if not api_key:
        return []
    try:
        genai.configure(api_key=api_key)
        models = genai.list_models()  # type: ignore
        names: list[str] = []
        for m in models:
            name = getattr(m, "name", None)
            if name:
                names.append(name)
        return names
    except Exception:
        return []


def generate_initial_docs(start: str | Path | None = None) -> bool:
    """Generate docs/ if missing. Returns True if files created/changed."""
    root = repo_root(Path(start) if start else None)
    repo = read_json(root / "repo_info.json")
    if not repo:
        return False
    docs = root / "docs"
    if docs.exists():
        return False

    model = _gemini_client()
    prompts = _load_bundled_prompts()

    api_md = _render_api_markdown(repo)

    if model:
        print("[docai] Generating overview with Gemini...")
        overview_md = _call_gemini(model, prompts.get("overview", ""), repo) or "# Overview\n\nProject overview."
        print("[docai] Generating README with Gemini...")
        readme_md = _call_gemini(model, prompts.get("readme", ""), repo) or "# README\n\nGetting started."
        # Use Gemini for API reference with fallback to deterministic renderer
        print("[docai] Generating API reference with Gemini...")
        api_md_gemini = _call_gemini(model, prompts.get("api", ""), repo)
        if api_md_gemini.strip():
            api_md = api_md_gemini
        else:
            print("[docai] Gemini API reference empty; using deterministic renderer.")
    else:
        overview_md = "# Overview\n\nGemini not configured. Place a config.json with your API key in the tool's root folder.\n"
        readme_md = "# README\n\nInstall dependencies and run your project.\n"

    _ensure_dir(docs)
    _write_text(docs / "overview.md", overview_md)
    _write_text(docs / "readme.md", readme_md)
    _write_text(docs / "api_reference.md", api_md)
    return True
