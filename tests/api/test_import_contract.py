from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import get_type_hints

import lenslet.server as server
import lenslet.storage.table as table
import lenslet.web.media as media
from lenslet.storage.base import BrowseAppStorage
from lenslet.web.app.builder import BrowseAppContextInputs
from lenslet.web.app.options import StorageMode
from lenslet.web.app.storage import StorageAppIdentity
from lenslet.web.context import AppContext


SERVER_SYMBOLS = (
    "create_app",
    "create_app_from_datasets",
    "create_app_from_table",
    "create_app_from_storage",
    "HotpathTelemetry",
    "LocalAppOptions",
    "DatasetAppOptions",
    "TableAppOptions",
    "StorageAppOptions",
    "og",
)

MEDIA_SYMBOLS = (
    "file_response",
    "thumb_response_async",
)

TABLE_SYMBOLS = (
    "TableStorage",
    "TableStorageOptions",
    "TableInput",
    "is_table_input",
    "validate_table_input",
    "load_parquet_table",
    "load_parquet_schema",
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC_ROOT = REPO_ROOT / "frontend" / "src"
FRONTEND_APP_ROOT = FRONTEND_SRC_ROOT / "app"
FRONTEND_DOWNSTREAM_ROOTS = (
    FRONTEND_SRC_ROOT / "features",
    FRONTEND_SRC_ROOT / "shared",
)
RANKING_FEATURE_ROOT = FRONTEND_SRC_ROOT / "features" / "ranking"
FRONTEND_API_CLIENT = FRONTEND_SRC_ROOT / "api" / "client.ts"
FILE_MUTATION_CLIENT_METHODS = {
    "uploadFile": "/file",
    "moveFile": "/move",
    "deleteFiles": "/delete",
    "exportIntent": "/export-intent",
}
ALLOWED_RANKING_SHARED_IMPORTS = {
    "../../api/base",
    "../../lib/cssVars",
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
    REPO_ROOT / "src" / "lenslet" / "web" / "routes" / "events.py",
    REPO_ROOT / "src" / "lenslet" / "web" / "routes" / "export.py",
    REPO_ROOT / "src" / "lenslet" / "web" / "routes" / "folders.py",
    REPO_ROOT / "src" / "lenslet" / "web" / "routes" / "index.py",
    REPO_ROOT / "src" / "lenslet" / "web" / "routes" / "items.py",
    REPO_ROOT / "src" / "lenslet" / "web" / "routes" / "media.py",
    REPO_ROOT / "src" / "lenslet" / "web" / "routes" / "og.py",
    REPO_ROOT / "src" / "lenslet" / "web" / "routes" / "views.py",
    REPO_ROOT / "src" / "lenslet" / "web" / "routes" / "search.py",
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
LEGACY_WEB_APP_ASSEMBLY_FILES = (
    REPO_ROOT / "src" / "lenslet" / "web" / "app_base.py",
    REPO_ROOT / "src" / "lenslet" / "web" / "app_builder.py",
    REPO_ROOT / "src" / "lenslet" / "web" / "app_options.py",
    REPO_ROOT / "src" / "lenslet" / "web" / "factory.py",
    REPO_ROOT / "src" / "lenslet" / "web" / "factory_health.py",
)
LEGACY_ROOT_IMPLEMENTATION_FILES = (
    REPO_ROOT / "src" / "lenslet" / "cli.py",
    REPO_ROOT / "src" / "lenslet" / "cli_browse.py",
    REPO_ROOT / "src" / "lenslet" / "cli_browse_args.py",
    REPO_ROOT / "src" / "lenslet" / "cli_common.py",
    REPO_ROOT / "src" / "lenslet" / "cli_rank.py",
    REPO_ROOT / "src" / "lenslet" / "cli_share.py",
    REPO_ROOT / "src" / "lenslet" / "preindex.py",
)
CLI_PREINDEX_PACKAGE_FILES = (
    REPO_ROOT / "src" / "lenslet" / "cli" / "__init__.py",
    REPO_ROOT / "src" / "lenslet" / "cli" / "__main__.py",
    REPO_ROOT / "src" / "lenslet" / "cli" / "main.py",
    REPO_ROOT / "src" / "lenslet" / "cli" / "browse.py",
    REPO_ROOT / "src" / "lenslet" / "cli" / "browse_args.py",
    REPO_ROOT / "src" / "lenslet" / "cli" / "common.py",
    REPO_ROOT / "src" / "lenslet" / "cli" / "rank.py",
    REPO_ROOT / "src" / "lenslet" / "cli" / "share.py",
    REPO_ROOT / "src" / "lenslet" / "storage" / "local" / "__init__.py",
    REPO_ROOT / "src" / "lenslet" / "storage" / "local" / "preindex.py",
)
WEB_RUNTIME_FILES = (
    REPO_ROOT / "src" / "lenslet" / "web" / "app" / "__init__.py",
    REPO_ROOT / "src" / "lenslet" / "web" / "app" / "base.py",
    REPO_ROOT / "src" / "lenslet" / "web" / "app" / "builder.py",
    REPO_ROOT / "src" / "lenslet" / "web" / "app" / "factory.py",
    REPO_ROOT / "src" / "lenslet" / "web" / "app" / "health.py",
    REPO_ROOT / "src" / "lenslet" / "web" / "app" / "options.py",
    REPO_ROOT / "src" / "lenslet" / "web" / "browse.py",
    REPO_ROOT / "src" / "lenslet" / "web" / "context.py",
    REPO_ROOT / "src" / "lenslet" / "web" / "export" / "__init__.py",
    REPO_ROOT / "src" / "lenslet" / "web" / "export" / "rendering.py",
    REPO_ROOT / "src" / "lenslet" / "web" / "export" / "response.py",
    REPO_ROOT / "src" / "lenslet" / "web" / "frontend.py",
    REPO_ROOT / "src" / "lenslet" / "web" / "generation.py",
    REPO_ROOT / "src" / "lenslet" / "web" / "lifecycle.py",
    REPO_ROOT / "src" / "lenslet" / "web" / "media.py",
    REPO_ROOT / "src" / "lenslet" / "web" / "paths.py",
    REPO_ROOT / "src" / "lenslet" / "web" / "og" / "__init__.py",
    REPO_ROOT / "src" / "lenslet" / "web" / "og" / "data.py",
    REPO_ROOT / "src" / "lenslet" / "web" / "og" / "rendering.py",
    REPO_ROOT / "src" / "lenslet" / "web" / "og" / "style.py",
    REPO_ROOT / "src" / "lenslet" / "web" / "presence_runtime.py",
    REPO_ROOT / "src" / "lenslet" / "web" / "record_update.py",
    REPO_ROOT / "src" / "lenslet" / "web" / "request_headers.py",
    REPO_ROOT / "src" / "lenslet" / "web" / "runtime.py",
    REPO_ROOT / "src" / "lenslet" / "web" / "sidecars.py",
    REPO_ROOT / "src" / "lenslet" / "web" / "time.py",
    REPO_ROOT / "src" / "lenslet" / "web" / "sync" / "__init__.py",
    REPO_ROOT / "src" / "lenslet" / "web" / "sync" / "events.py",
    REPO_ROOT / "src" / "lenslet" / "web" / "sync" / "labels.py",
    REPO_ROOT / "src" / "lenslet" / "web" / "sync" / "presence.py",
    REPO_ROOT / "src" / "lenslet" / "web" / "routes" / "common.py",
    REPO_ROOT / "src" / "lenslet" / "web" / "routes" / "index.py",
    REPO_ROOT / "src" / "lenslet" / "web" / "routes" / "events.py",
    REPO_ROOT / "src" / "lenslet" / "web" / "routes" / "export.py",
    REPO_ROOT / "src" / "lenslet" / "web" / "routes" / "folders.py",
    REPO_ROOT / "src" / "lenslet" / "web" / "routes" / "items.py",
    REPO_ROOT / "src" / "lenslet" / "web" / "routes" / "media.py",
    REPO_ROOT / "src" / "lenslet" / "web" / "routes" / "og.py",
    REPO_ROOT / "src" / "lenslet" / "web" / "routes" / "presence.py",
    REPO_ROOT / "src" / "lenslet" / "web" / "routes" / "search.py",
    REPO_ROOT / "src" / "lenslet" / "web" / "routes" / "views.py",
    REPO_ROOT / "src" / "lenslet" / "web" / "cache" / "browse.py",
    REPO_ROOT / "src" / "lenslet" / "web" / "cache" / "og.py",
    REPO_ROOT / "src" / "lenslet" / "web" / "cache" / "thumbs.py",
)


def _run_import_probe(script: str) -> None:
    env = os.environ.copy()
    src_path = str(REPO_ROOT / "src")
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        f"{src_path}{os.pathsep}{existing_pythonpath}" if existing_pythonpath else src_path
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr + result.stdout


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


def _iter_frontend_source_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*") if path.suffix in {".ts", ".tsx"})


def _route_methods(app: object) -> set[tuple[str, str]]:
    route_methods: set[tuple[str, str]] = set()
    for route in getattr(app, "routes", []):
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if not path or not methods:
            continue
        for method in methods:
            route_methods.add((method, path))
    return route_methods


def test_server_import_contract_symbols() -> None:
    for symbol in SERVER_SYMBOLS:
        assert hasattr(server, symbol), f"missing lenslet.server import-contract symbol: {symbol}"
    assert hasattr(server.og, "subtree_image_count"), "missing lenslet.server.og.subtree_image_count"


def test_server_facade_import_does_not_load_optional_rendering_stack() -> None:
    _run_import_probe(
        """
import sys
import lenslet.server as server

assert hasattr(server, "create_app")
assert hasattr(server, "og")
assert "lenslet.web.og.rendering" not in sys.modules
assert "lenslet.web.app.local" not in sys.modules
assert "lenslet.storage.local.preindex" not in sys.modules
assert "lenslet.storage.table.storage" not in sys.modules
pil_modules = [name for name in sys.modules if name == "PIL" or name.startswith("PIL.")]
assert pil_modules == [], pil_modules
"""
    )


def test_programmatic_api_import_promotes_server_dependencies_without_rendering_stack() -> None:
    _run_import_probe(
        """
import sys
import lenslet.api as api

assert callable(api.launch)
assert callable(api.launch_table)
assert "lenslet.server" in sys.modules
assert "lenslet.web.og.rendering" not in sys.modules
pil_modules = [name for name in sys.modules if name == "PIL" or name.startswith("PIL.")]
assert pil_modules == [], pil_modules
"""
    )


def test_optional_dependency_boundary_modules_import_without_heavy_runtime_imports() -> None:
    _run_import_probe(
        """
import sys
import lenslet.embeddings.cache
import lenslet.embeddings.detect
import lenslet.embeddings.index
import lenslet.embeddings.io
import lenslet.storage.table.launch
import lenslet.storage.table.launch_sources
import lenslet.storage.source.media
import lenslet.ranking.persistence

blocked_prefixes = ("numpy", "faiss", "pyarrow")
loaded = [
    name
    for name in sys.modules
    if any(name == prefix or name.startswith(f"{prefix}.") for prefix in blocked_prefixes)
]
assert loaded == [], loaded
assert "boto3" not in sys.modules
"""
    )


def test_create_app_from_storage_advertises_full_browse_app_contract() -> None:
    hints = get_type_hints(server.create_app_from_storage)

    assert hints["storage"] is BrowseAppStorage


def test_table_import_contract_symbols() -> None:
    for symbol in TABLE_SYMBOLS:
        assert hasattr(table, symbol), f"missing lenslet.storage.table import-contract symbol: {symbol}"


def test_public_init_uses_future_annotations() -> None:
    init_text = (REPO_ROOT / "src" / "lenslet" / "__init__.py").read_text(encoding="utf-8")
    assert "from __future__ import annotations" in init_text


def test_storage_mode_contexts_use_literal_alias() -> None:
    assert get_type_hints(AppContext)["storage_mode"] == StorageMode
    assert get_type_hints(BrowseAppContextInputs)["storage_mode"] == StorageMode
    assert get_type_hints(StorageAppIdentity)["mode"] == StorageMode


def test_media_import_contract_symbols() -> None:
    for symbol in MEDIA_SYMBOLS:
        assert hasattr(media, symbol), f"missing lenslet.web.media import-contract symbol: {symbol}"


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


def test_frontend_features_and_shared_do_not_import_app_layer() -> None:
    violations: list[str] = []
    for root in FRONTEND_DOWNSTREAM_ROOTS:
        assert root.exists(), f"expected frontend source root to exist: {root.relative_to(REPO_ROOT)}"
        for source_file in _iter_frontend_source_files(root):
            for specifier in _iter_import_specifiers(source_file):
                if specifier.startswith("."):
                    resolved = (source_file.parent / specifier).resolve()
                    if resolved.is_relative_to(FRONTEND_APP_ROOT):
                        violations.append(
                            f"{source_file.relative_to(REPO_ROOT)} -> {specifier} resolves into app layer"
                        )
                    continue
                if specifier == "app" or specifier.startswith("app/"):
                    violations.append(
                        f"{source_file.relative_to(REPO_ROOT)} -> {specifier} imports app layer"
                    )

    assert not violations, "frontend downstream import-contract violations:\n" + "\n".join(
        sorted(violations)
    )


def test_frontend_client_does_not_advertise_unregistered_file_mutations(tmp_path: Path) -> None:
    client_text = FRONTEND_API_CLIENT.read_text(encoding="utf-8")
    route_methods = _route_methods(server.create_app(str(tmp_path)))

    assert ("GET", "/file") in route_methods
    assert ("POST", "/export-comparison") in route_methods

    violations: list[str] = []
    for method_name, route_path in FILE_MUTATION_CLIENT_METHODS.items():
        if ("POST", route_path) in route_methods:
            continue
        if method_name in client_text:
            violations.append(f"{method_name} advertises missing POST {route_path}")
        route_literal_tokens = (
            f"`${{BASE}}{route_path}`",
            f"'{route_path}'",
            f'"{route_path}"',
        )
        if any(token in client_text for token in route_literal_tokens):
            violations.append(f"frontend client references missing POST {route_path}")

    assert not violations, "frontend/backend file mutation route drift:\n" + "\n".join(violations)


def test_sprint1_route_modules_do_not_depend_on_server_facade() -> None:
    violations: list[str] = []
    for file_path in SPRINT1_ROUTE_FILES:
        text = file_path.read_text(encoding="utf-8")
        if "from . import server" in text or "from .server import" in text:
            violations.append(str(file_path.relative_to(REPO_ROOT)))
    assert not violations, "route modules still depend on lenslet.server:\n" + "\n".join(violations)


def test_web_runtime_package_structure_contract() -> None:
    lingering = [
        path.relative_to(REPO_ROOT)
        for path in (*LEGACY_WEB_ROOT_FILES, *LEGACY_WEB_APP_ASSEMBLY_FILES)
        if path.exists()
    ]
    assert not lingering, "root package still exposes moved web implementation files:\n" + "\n".join(map(str, lingering))

    missing = [path.relative_to(REPO_ROOT) for path in WEB_RUNTIME_FILES if not path.exists()]
    assert not missing, "expected web runtime package files are missing:\n" + "\n".join(map(str, missing))


def test_presence_prune_runtime_dependency_is_injected_from_app_assembly() -> None:
    presence_runtime = (REPO_ROOT / "src" / "lenslet" / "web" / "presence_runtime.py").read_text(
        encoding="utf-8"
    )
    app_builder = (REPO_ROOT / "src" / "lenslet" / "web" / "app" / "builder.py").read_text(
        encoding="utf-8"
    )
    runtime = (REPO_ROOT / "src" / "lenslet" / "web" / "runtime.py").read_text(encoding="utf-8")

    assert "from .context import" not in presence_runtime
    assert "get_app_context" not in presence_runtime
    assert "install_presence_prune_loop(" in app_builder
    assert "get_app_runtime(app)" in app_builder
    assert "from .presence_runtime import PresenceMetrics" not in runtime


def test_cli_and_preindex_package_structure_contract() -> None:
    lingering = [
        path.relative_to(REPO_ROOT)
        for path in LEGACY_ROOT_IMPLEMENTATION_FILES
        if path.exists()
    ]
    assert not lingering, "package root still exposes moved CLI/preindex files:\n" + "\n".join(map(str, lingering))

    missing = [path.relative_to(REPO_ROOT) for path in CLI_PREINDEX_PACKAGE_FILES if not path.exists()]
    assert not missing, "expected CLI/preindex package files are missing:\n" + "\n".join(map(str, missing))

    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'lenslet = "lenslet.cli.main:main"' in pyproject
