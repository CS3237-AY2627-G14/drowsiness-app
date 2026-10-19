import ast
from collections.abc import Iterator
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_DEPENDENCIES: dict[str, set[str]] = {
    "classrooms": set(),
    "sessions": {"classrooms"},
    "streaming": {"sessions", "processing"},
    "devices": {"classrooms", "sessions"},
    "processing": set(),
}


def imported_modules(path: Path) -> Iterator[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, f"Use absolute imports: {path}:{node.lineno}"
            if node.module is not None:
                yield node.module


def test_module_boundaries_and_dependency_cycles() -> None:
    graph: dict[str, set[str]] = {name: set() for name in ALLOWED_DEPENDENCIES}
    for path in (ROOT / "modules").rglob("*.py"):
        relative = path.relative_to(ROOT)
        if len(relative.parts) < 3:
            continue
        source = relative.parts[1]
        assert source in ALLOWED_DEPENDENCIES, f"Declare dependencies for {source}"
        for imported in imported_modules(path):
            parts = imported.split(".")
            if len(parts) < 2 or parts[0] != "modules" or parts[1] == source:
                continue
            target = parts[1]
            assert target in ALLOWED_DEPENDENCIES[source], (
                f"Prohibited dependency: {relative} imports {imported}"
            )
            assert len(parts) == 3 and parts[2] == "facade", (
                f"Import through the module facade: {relative} imports {imported}"
            )
            graph[source].add(target)

    def visit(module: str, ancestors: frozenset[str]) -> None:
        assert module not in ancestors, f"Dependency cycle through {module}"
        for target in graph[module]:
            visit(target, ancestors | {module})

    for module in graph:
        visit(module, frozenset())


def test_core_does_not_import_business_modules() -> None:
    for path in (ROOT / "core").rglob("*.py"):
        for imported in imported_modules(path):
            assert imported.split(".")[0] != "modules", f"Core imports {imported}"


def test_services_and_repositories_are_framework_independent() -> None:
    for path in (ROOT / "modules").rglob("*.py"):
        if (
            path.name
            not in {
                "service.py",
                "repository.py",
                "registry.py",
                "frame_buffer.py",
                "facade.py",
            }
            and "services" not in path.parts
            and "repositories" not in path.parts
        ):
            continue
        for imported in imported_modules(path):
            assert imported.split(".")[0] not in {
                "fastapi",
                "starlette",
                "sqlalchemy",
            }, f"Framework dependency in {path.relative_to(ROOT)}: {imported}"
