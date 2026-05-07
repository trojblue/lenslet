from __future__ import annotations

import re
from pathlib import Path

import lenslet.server as server
import lenslet.storage.table as table


SERVER_SYMBOLS = (
    "create_app",
    "create_app_from_datasets",
    "create_app_from_table",
    "create_app_from_storage",
    "HotpathTelemetry",
    "_file_response",
    "_thumb_response_async",
    "og",
)

TABLE_SYMBOLS = (
    "TableStorage",
    "load_parquet_table",
    "load_parquet_schema",
)

REPO_ROOT = Path(__file__).resolve().parents[1]
RANKING_FEATURE_ROOT = REPO_ROOT / "frontend" / "src" / "features" / "ranking"
ALLOWED_RANKING_SHARED_IMPORTS = {
    "../../api/base",
    "../../lib/fetcher",
}
ALLOWED_RANKING_BARE_IMPORTS = {
    "@dnd-kit/core",
    "@dnd-kit/sortable",
    "@dnd-kit/utilities",
    "lucide-react",
    "react",
    "vitest",
}
IMPORT_SPECIFIER_PATTERN = re.compile(
    r"""^\s*[\w{}\s,*]*\sfrom\s+["'](?P<from>[^"']+)["']|^\s*import\s+["'](?P<side>[^"']+)["']""",
    re.MULTILINE,
)
DYNAMIC_IMPORT_PATTERN = re.compile(
    r"""import\(\s*["'](?P<dynamic>[^"']+)["']\s*\)"""
)
SPRINT1_ROUTE_FILES = (
    REPO_ROOT / "src" / "lenslet" / "web" / "routes" / "common.py",
    REPO_ROOT / "src" / "lenslet" / "web" / "routes" / "index.py",
    REPO_ROOT / "src" / "lenslet" / "web" / "routes" / "og.py",
    REPO_ROOT / "src" / "lenslet" / "web" / "routes" / "views.py",
)
LEGACY_WEB_ROOT_FILES = (
    REPO_ROOT / "src" / "lenslet" / "app_base.py",
    REPO_ROOT / "src" / "lenslet" / "browse_app_builder.py",
    REPO_ROOT / "src" / "lenslet" / "browse_cache.py",
    REPO_ROOT / "src" / "lenslet" / "frontend_serving.py",
    REPO_ROOT / "src" / "lenslet" / "og_cache.py",
    REPO_ROOT / "src" / "lenslet" / "server_auth.py",
    REPO_ROOT / "src" / "lenslet" / "server_browse.py",
    REPO_ROOT / "src" / "lenslet" / "server_context.py",
    REPO_ROOT / "src" / "lenslet" / "server_factory.py",
    REPO_ROOT / "src" / "lenslet" / "server_media.py",
    REPO_ROOT / "src" / "lenslet" / "server_models.py",
    REPO_ROOT / "src" / "lenslet" / "server_permissions.py",
    REPO_ROOT / "src" / "lenslet" / "server_routes_common.py",
    REPO_ROOT / "src" / "lenslet" / "server_routes_embeddings.py",
    REPO_ROOT / "src" / "lenslet" / "server_routes_index.py",
    REPO_ROOT / "src" / "lenslet" / "server_routes_og.py",
    REPO_ROOT / "src" / "lenslet" / "server_routes_presence.py",
    REPO_ROOT / "src" / "lenslet" / "server_routes_views.py",
    REPO_ROOT / "src" / "lenslet" / "server_runtime.py",
    REPO_ROOT / "src" / "lenslet" / "server_sync.py",
    REPO_ROOT / "src" / "lenslet" / "thumb_cache.py",
)
WEB_RUNTIME_FILES = (
    REPO_ROOT / "src" / "lenslet" / "web" / "factory.py",
    REPO_ROOT / "src" / "lenslet" / "web" / "browse.py",
    REPO_ROOT / "src" / "lenslet" / "web" / "context.py",
    REPO_ROOT / "src" / "lenslet" / "web" / "media.py",
    REPO_ROOT / "src" / "lenslet" / "web" / "runtime.py",
    REPO_ROOT / "src" / "lenslet" / "web" / "sync.py",
    REPO_ROOT / "src" / "lenslet" / "web" / "routes" / "common.py",
    REPO_ROOT / "src" / "lenslet" / "web" / "routes" / "index.py",
    REPO_ROOT / "src" / "lenslet" / "web" / "routes" / "og.py",
    REPO_ROOT / "src" / "lenslet" / "web" / "routes" / "presence.py",
    REPO_ROOT / "src" / "lenslet" / "web" / "routes" / "views.py",
    REPO_ROOT / "src" / "lenslet" / "web" / "cache" / "browse.py",
    REPO_ROOT / "src" / "lenslet" / "web" / "cache" / "og.py",
    REPO_ROOT / "src" / "lenslet" / "web" / "cache" / "thumbs.py",
)


def _iter_import_specifiers(file_path: Path) -> list[str]:
    text = file_path.read_text(encoding="utf-8")
    specifiers: list[str] = []
    for match in IMPORT_SPECIFIER_PATTERN.finditer(text):
        specifier = match.group("from") or match.group("side")
        if specifier:
            specifiers.append(specifier)
    for match in DYNAMIC_IMPORT_PATTERN.finditer(text):
        specifier = match.group("dynamic")
        if specifier:
            specifiers.append(specifier)
    return specifiers


def _is_ranking_test_file(file_path: Path) -> bool:
    if "__tests__" in file_path.parts:
        return True
    return file_path.name.endswith(".test.ts") or file_path.name.endswith(".test.tsx")


def test_server_import_contract_symbols() -> None:
    for symbol in SERVER_SYMBOLS:
        assert hasattr(server, symbol), f"missing lenslet.server import-contract symbol: {symbol}"
    assert hasattr(server.og, "subtree_image_count"), "missing lenslet.server.og.subtree_image_count"


def test_table_import_contract_symbols() -> None:
    for symbol in TABLE_SYMBOLS:
        assert hasattr(table, symbol), f"missing lenslet.storage.table import-contract symbol: {symbol}"


def test_ranking_frontend_import_contract() -> None:
    feature_root = RANKING_FEATURE_ROOT.resolve()
    ranking_files = sorted(feature_root.rglob("*.ts")) + sorted(feature_root.rglob("*.tsx"))
    assert ranking_files, "expected ranking frontend sources to exist for import contract check"

    violations: list[str] = []
    for source_file in ranking_files:
        is_test_file = _is_ranking_test_file(source_file)
        for specifier in _iter_import_specifiers(source_file):
            if specifier in ALLOWED_RANKING_SHARED_IMPORTS:
                continue
            if specifier.startswith("."):
                resolved = (source_file.parent / specifier).resolve()
                if resolved.is_relative_to(feature_root):
                    continue
                violations.append(
                    f"{source_file.relative_to(REPO_ROOT)} -> {specifier} resolves outside ranking feature"
                )
                continue
            if specifier == "vitest":
                if is_test_file:
                    continue
                violations.append(
                    f"{source_file.relative_to(REPO_ROOT)} -> vitest import is only allowed in ranking test files"
                )
                continue
            if specifier in ALLOWED_RANKING_BARE_IMPORTS:
                continue
            violations.append(
                f"{source_file.relative_to(REPO_ROOT)} -> {specifier} not in ranking import allowlist"
            )

    assert not violations, "ranking import contract violations:\n" + "\n".join(sorted(violations))


def test_sprint1_route_modules_do_not_depend_on_server_facade() -> None:
    violations: list[str] = []
    for file_path in SPRINT1_ROUTE_FILES:
        text = file_path.read_text(encoding="utf-8")
        if "from . import server" in text or "from .server import" in text:
            violations.append(str(file_path.relative_to(REPO_ROOT)))
    assert not violations, "route modules still depend on lenslet.server:\n" + "\n".join(violations)


def test_web_runtime_package_structure_contract() -> None:
    lingering = [path.relative_to(REPO_ROOT) for path in LEGACY_WEB_ROOT_FILES if path.exists()]
    assert not lingering, "root package still exposes moved web implementation files:\n" + "\n".join(map(str, lingering))

    missing = [path.relative_to(REPO_ROOT) for path in WEB_RUNTIME_FILES if not path.exists()]
    assert not missing, "expected web runtime package files are missing:\n" + "\n".join(map(str, missing))
