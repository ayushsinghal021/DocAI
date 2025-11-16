from __future__ import annotations

import ast
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from .util import iter_python_files, repo_root, write_json


@dataclass
class FunctionInfo:
    name: str
    args: List[Dict[str, Optional[str]]]
    returns: Optional[str]
    defaults: Dict[str, str]
    decorators: List[str]
    is_async: bool
    doc: str | None
    summary: str


@dataclass
class ClassInfo:
    name: str
    bases: List[str]
    decorators: List[str]
    doc: str | None
    attributes: List[Dict[str, Optional[str]]]
    methods: List[FunctionInfo]
    summary: str


@dataclass
class FileInfo:
    path: str
    module: str
    module_doc: Optional[str]
    imports: List[str]
    classes: List[ClassInfo]
    functions: List[FunctionInfo]
    summary: str


@dataclass
class RepoInfo:
    root: str
    files: List[FileInfo]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "root": self.root,
            "files": [asdict(f) for f in self.files],
        }


def _doc_summary(doc: str | None) -> str:
    if doc:
        first = doc.strip().splitlines()[0].strip()
        return first[:160]
    return "No docstring provided."

def _unparse_safe(n: ast.AST) -> str:
    try:
        return ast.unparse(n)  # type: ignore[attr-defined]
    except Exception:
        return getattr(n, "id", None) or getattr(n, "arg", None) or type(n).__name__


def _func_info(node: ast.FunctionDef | ast.AsyncFunctionDef) -> FunctionInfo:
    arg_items: List[Dict[str, Optional[str]]] = []
    for a in node.args.args:
        ann = _unparse_safe(a.annotation) if getattr(a, "annotation", None) else None
        arg_items.append({"name": a.arg, "annotation": ann})

    # defaults align with last N args
    defaults: Dict[str, str] = {}
    if node.args.defaults:
        pos_args = node.args.args
        for name, d in zip([a.arg for a in pos_args[-len(node.args.defaults):]], node.args.defaults):
            defaults[name] = _unparse_safe(d)

    returns: Optional[str] = None
    if getattr(node, "returns", None):
        returns = _unparse_safe(node.returns)  # type: ignore[arg-type]

    decorators: List[str] = []
    for d in getattr(node, "decorator_list", []) or []:
        decorators.append(_unparse_safe(d))

    doc = ast.get_docstring(node)
    sig_preview = ", ".join([i["name"] for i in arg_items])
    summary = _doc_summary(doc) if doc else f"Function {node.name}({sig_preview})"
    return FunctionInfo(
        name=node.name,
        args=arg_items,
        returns=returns,
        defaults=defaults,
        decorators=decorators,
        is_async=isinstance(node, ast.AsyncFunctionDef),
        doc=doc,
        summary=summary,
    )


def _class_info(node: ast.ClassDef) -> ClassInfo:
    bases = []
    for b in node.bases:
        bases.append(_unparse_safe(b))
    decorators: List[str] = []
    for d in node.decorator_list:
        decorators.append(_unparse_safe(d))
    methods: List[FunctionInfo] = []
    attributes: List[Dict[str, Optional[str]]] = []
    for n in node.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            methods.append(_func_info(n))
        elif isinstance(n, ast.AnnAssign):
            target = _unparse_safe(n.target)
            ann = _unparse_safe(n.annotation) if n.annotation else None
            attributes.append({"name": target, "annotation": ann})
        elif isinstance(n, ast.Assign):
            # simple attribute names
            for t in n.targets:
                name = _unparse_safe(t)
                attributes.append({"name": name, "annotation": None})
    doc = ast.get_docstring(node)
    mcount = len(methods)
    summary = _doc_summary(doc) if doc else f"Class {node.name} with {mcount} methods"
    return ClassInfo(
        name=node.name,
        bases=bases,
        decorators=decorators,
        doc=doc,
        attributes=attributes,
        methods=methods,
        summary=summary,
    )


def _module_name(root: Path, file: Path) -> str:
    rel = file.relative_to(root).with_suffix("")
    return ".".join(rel.parts)


def scan_repository(start: str | Path | None = None, out_path: str | Path | None = None) -> RepoInfo:
    root = repo_root(Path(start) if start else None)
    files: List[FileInfo] = []
    for py in iter_python_files(root):
        try:
            source = py.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except Exception:
            # Skip files that can't be parsed
            continue
        # Gather imports
        imports: List[str] = []
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                for alias in n.names:
                    imports.append(alias.name)
            elif isinstance(n, ast.ImportFrom):
                mod = n.module or ""
                for alias in n.names:
                    imports.append(f"{mod}.{alias.name}" if mod else alias.name)
        classes: List[ClassInfo] = []
        functions: List[FunctionInfo] = []
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                classes.append(_class_info(node))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append(_func_info(node))
        mod = _module_name(root, py)
        file_doc = ast.get_docstring(tree)
        summary = _doc_summary(file_doc) if file_doc else (
            f"Module {mod} with {len(classes)} classes and {len(functions)} functions"
        )
        files.append(FileInfo(
            path=str(py.relative_to(root)),
            module=mod,
            module_doc=file_doc,
            imports=sorted(set(imports)),
            classes=classes,
            functions=functions,
            summary=summary,
        ))

    repo = RepoInfo(root=str(root), files=files)
    out = Path(out_path) if out_path else root / "repo_info.json"
    write_json(out, repo.to_dict())
    return repo
