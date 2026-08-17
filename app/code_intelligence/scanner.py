"""
Repository code-intelligence scanner.

Goes beyond exact string matching:
  1. Repository scanner (walks sample_app/)
  2. AST parsing per file
  3. Function / class detection with line ranges
  4. Exception detection (raise statements + exception types)
  5. Error-message -> symbol matching (keyword overlap + literal match)
  6. Service-to-source mapping (service name -> sample_app/services/<service>/)
  7. Symbol/function matching returned as structured evidence
"""
from __future__ import annotations

import ast
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from app.config import get_settings

logger = logging.getLogger("erca_ris.code_intelligence")
settings = get_settings()

SERVICE_ALIASES = {
    "payment": "payment", "payments": "payment",
    "auth": "auth", "authentication": "auth",
    "orders": "orders", "order": "orders",
    "inventory": "inventory",
    "notification": "notification", "notifications": "notification", "email": "notification",
    "search": "search",
    "storage": "storage",
    "reports": "reports", "reporting": "reports", "report": "reports",
}


@dataclass
class Symbol:
    kind: str  # function | class
    name: str
    lineno: int
    end_lineno: int


@dataclass
class RaisedException:
    exception_type: str
    lineno: int
    message: str | None
    function: str | None


@dataclass
class FileIndex:
    path: Path
    source: str
    lines: list[str] = field(default_factory=list)
    symbols: list[Symbol] = field(default_factory=list)
    exceptions: list[RaisedException] = field(default_factory=list)


def service_dir_for(service: str | None) -> Path | None:
    if not service:
        return None
    key = re.sub(r"[^a-z]", "", service.lower())
    for alias, folder in SERVICE_ALIASES.items():
        if alias in key:
            candidate = settings.SOURCE_ROOT / "services" / folder
            if candidate.exists():
                return candidate
    return None


def _index_file(path: Path) -> FileIndex | None:
    try:
        source = path.read_text()
    except Exception as exc:
        logger.warning("Could not read %s: %s", path, exc)
        return None

    idx = FileIndex(path=path, source=source, lines=source.splitlines())

    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        logger.warning("Syntax error parsing %s: %s", path, exc)
        return idx

    current_function_stack: list[tuple[int, int, str]] = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            idx.symbols.append(Symbol("function", node.name, node.lineno, getattr(node, "end_lineno", node.lineno)))
        elif isinstance(node, ast.ClassDef):
            idx.symbols.append(Symbol("class", node.name, node.lineno, getattr(node, "end_lineno", node.lineno)))
        elif isinstance(node, ast.Raise):
            exc_type = None
            message = None
            exc_node = node.exc
            if isinstance(exc_node, ast.Call):
                if isinstance(exc_node.func, ast.Name):
                    exc_type = exc_node.func.id
                elif isinstance(exc_node.func, ast.Attribute):
                    exc_type = exc_node.func.attr
                if exc_node.args:
                    first_arg = exc_node.args[0]
                    if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
                        message = first_arg.value
            elif isinstance(exc_node, ast.Name):
                exc_type = exc_node.id

            enclosing = _enclosing_function(idx.symbols, node.lineno)
            idx.exceptions.append(RaisedException(
                exception_type=exc_type or "Exception",
                lineno=node.lineno,
                message=message,
                function=enclosing,
            ))

    return idx


def _enclosing_function(symbols: list[Symbol], lineno: int) -> str | None:
    best = None
    for sym in symbols:
        if sym.kind == "function" and sym.lineno <= lineno <= sym.end_lineno:
            if best is None or sym.lineno > best.lineno:
                best = sym
    return best.name if best else None


def _scan_root(root: Path) -> list[FileIndex]:
    results = []
    if not root.exists():
        return results
    for path in root.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        idx = _index_file(path)
        if idx:
            results.append(idx)
    return results


def _score_match(error_message: str, idx: FileIndex, exc: RaisedException) -> float:
    """Heuristic relevance score combining literal + keyword overlap."""
    error_lower = (error_message or "").lower()
    score = 0.0

    if exc.message and exc.message.lower() in error_lower:
        score += 3.0
    if exc.message and error_lower in exc.message.lower():
        score += 2.0

    error_tokens = set(re.findall(r"[a-zA-Z]{3,}", error_lower))
    msg_tokens = set(re.findall(r"[a-zA-Z]{3,}", (exc.message or "").lower()))
    overlap = error_tokens & msg_tokens
    score += 0.4 * len(overlap)

    # Exception type keyword hints
    type_hints = {
        "TimeoutError": ["timeout", "timed"],
        "ConnectionError": ["connection", "unavailable", "unreachable"],
        "ValueError": ["invalid", "failed"],
        "PermissionError": ["permission", "denied", "unauthorized"],
    }
    for hint in type_hints.get(exc.exception_type, []):
        if hint in error_lower:
            score += 0.8

    return score


def find_error_in_repository(error_message: str, service: str | None = None) -> dict:
    """
    Locates the most likely source of `error_message`.

    Search order:
      1. Restrict to the mapped service directory if we can resolve one.
      2. Score every `raise` statement in scope against the error text.
      3. Fall back to scanning the whole sample_app/ tree.
      4. Fall back further to plain substring matching (legacy behaviour).
    """
    root = service_dir_for(service) or settings.SOURCE_ROOT
    file_indexes = _scan_root(root)
    if not file_indexes and root != settings.SOURCE_ROOT:
        file_indexes = _scan_root(settings.SOURCE_ROOT)

    best_score = 0.0
    best: dict | None = None

    for idx in file_indexes:
        for exc in idx.exceptions:
            score = _score_match(error_message, idx, exc)
            if score > best_score:
                best_score = score
                line_text = idx.lines[exc.lineno - 1].strip() if 0 < exc.lineno <= len(idx.lines) else ""
                best = {
                    "found": True,
                    "file": str(idx.path.relative_to(_project_root())),
                    "function": exc.function,
                    "line": exc.lineno,
                    "code": line_text,
                    "exception_type": exc.exception_type,
                    "match_score": round(score, 2),
                }

    if best and best_score > 0:
        return best

    # Fallback: plain substring match across the tree (legacy behaviour, still useful).
    needle = (error_message or "").strip().lower()
    for idx in file_indexes or _scan_root(settings.SOURCE_ROOT):
        for line_no, line in enumerate(idx.lines, 1):
            if needle and needle in line.lower():
                function = _enclosing_function(idx.symbols, line_no)
                return {
                    "found": True,
                    "file": str(idx.path.relative_to(_project_root())),
                    "function": function,
                    "line": line_no,
                    "code": line.strip(),
                    "exception_type": None,
                    "match_score": 1.0,
                }

    return {"found": False, "file": None, "function": None, "line": None, "code": None, "exception_type": None, "match_score": 0.0}


def _project_root() -> Path:
    return settings.SOURCE_ROOT.parent


def analyze_code(error_message: str, service: str | None = None) -> dict:
    return find_error_in_repository(error_message, service=service)
