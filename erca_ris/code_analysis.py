import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SOURCE_ROOT = PROJECT_ROOT / "sample_app"


def python_files():
    return SOURCE_ROOT.rglob("*.py")


def find_error_in_repository(error_message: str):
    needle = (error_message or "").strip().lower()
    if not needle:
        return None

    for path in python_files():
        try:
            source = path.read_text()
            lines = source.splitlines()
        except Exception:
            continue

        for line_no, line in enumerate(lines, 1):
            if needle in line.lower():
                function = None
                try:
                    tree = ast.parse(source)
                    for node in ast.walk(tree):
                        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            end = getattr(node, "end_lineno", node.lineno)
                            if node.lineno <= line_no <= end:
                                function = node.name
                                break
                except SyntaxError:
                    pass

                return {
                    "found": True,
                    "file": str(path.relative_to(PROJECT_ROOT)),
                    "line": line_no,
                    "code": line.strip(),
                    "function": function,
                }

    return None


def analyze_code(error_message: str):
    match = find_error_in_repository(error_message)
    if match:
        return match
    return {
        "found": False,
        "file": None,
        "line": None,
        "code": None,
        "function": None,
    }
