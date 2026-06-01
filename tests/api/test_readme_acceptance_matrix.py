from __future__ import annotations

import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

from lenslet.web.models import EmbeddingSearchRequest


REPO_ROOT = Path(__file__).resolve().parents[2]
TREE_ENTRY_RE = re.compile(r"^(?P<prefix>(?:│   |\s{4})*)(?:├──|└──) (?P<name>[^#]+)")
AGENTS_BROWSER_SMOKE_MODULES = (
    "scripts.browser.gui_smoke.acceptance",
    "scripts.browser.large_tree.smoke",
)
LEGACY_AGENTS_BROWSER_SMOKE_COMMANDS = (
    "python scripts/browser/gui_smoke/acceptance.py",
    "python scripts/browser/large_tree/smoke.py",
)


def _active_docs() -> list[Path]:
    return [
        REPO_ROOT / "README.md",
        REPO_ROOT / "DEVELOPMENT.md",
        REPO_ROOT / "QUICKSTART_API.md",
        *sorted((REPO_ROOT / "docs").glob("*.md")),
    ]


def _documented_acceptance_paths() -> list[str]:
    paths: list[str] = []
    for path in _active_docs():
        for documented_path in _acceptance_paths_from_doc(path):
            if documented_path not in paths:
                paths.append(documented_path)
    return paths


def _acceptance_paths_from_doc(path: Path) -> list[str]:
    paths: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not (line.startswith("pytest ") or line.startswith("npm run test ")):
            continue
        for token in shlex.split(line):
            if token.startswith("tests/") and token.endswith(".py"):
                paths.append(token)
            elif token.startswith("frontend/") and token.endswith((".ts", ".tsx")):
                paths.append(token)
            elif token.startswith("src/") and token.endswith((".ts", ".tsx")):
                paths.append(f"frontend/{token}")
    return paths


def _development_project_tree_paths() -> list[tuple[str, Path, bool]]:
    text = (REPO_ROOT / "DEVELOPMENT.md").read_text(encoding="utf-8")
    section = text.split("## Project Structure", maxsplit=1)[1]
    tree_block = section.split("```", maxsplit=2)[1]
    stack: list[str] = []
    paths: list[tuple[str, Path, bool]] = []

    for raw_line in tree_block.splitlines():
        match = TREE_ENTRY_RE.match(raw_line)
        if match is None:
            continue
        depth = len(match.group("prefix")) // 4
        raw_name = match.group("name").strip()
        is_dir = raw_name.endswith("/")
        name = raw_name.rstrip("/")
        stack = stack[:depth]
        parts = [*stack, name]
        paths.append(("/".join(parts), REPO_ROOT.joinpath(*parts), is_dir))
        stack = parts

    return paths


def test_active_docs_acceptance_matrix_references_existing_test_files() -> None:
    missing = [path for path in _documented_acceptance_paths() if not (REPO_ROOT / path).is_file()]
    assert not missing


def test_agents_browser_smoke_commands_use_module_entrypoints() -> None:
    agents = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")

    assert [command for command in LEGACY_AGENTS_BROWSER_SMOKE_COMMANDS if command in agents] == []

    for module in AGENTS_BROWSER_SMOKE_MODULES:
        assert f"python -m {module}" in agents
        completed = subprocess.run(
            [sys.executable, "-m", module, "--help"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr or completed.stdout


def test_development_project_tree_references_existing_paths() -> None:
    missing = [
        documented_path
        for documented_path, path, is_dir in _development_project_tree_paths()
        if not (path.is_dir() if is_dir else path.is_file())
    ]
    assert missing == []


def test_root_docs_do_not_reference_removed_backend_modules() -> None:
    docs = "\n".join(path.read_text(encoding="utf-8") for path in _active_docs())

    removed_references = [
        "legacy_recursive",
        "legacyRecursive",
        "page_size",
        "src/lenslet/cli.py",
        "src/lenslet/cli_browse.py",
        "src/lenslet/cli_rank.py",
        "src/lenslet/preindex.py",
        "src/lenslet/storage/dataset.py",
        "src/lenslet/storage/local.py",
        "src/lenslet/storage/memory.py",
        "src/lenslet/storage/preindex.py",
        "src/lenslet/storage/source_backed.py",
        "src/lenslet/storage/source_catalog.py",
        "src/lenslet/storage/source_media.py",
        "src/lenslet/storage/source_paths.py",
        "src/lenslet/storage/source_state.py",
        "src/lenslet/storage/table.py",
        "src/lenslet/storage/table_index.py",
        "src/lenslet/storage/table_launch.py",
        "src/lenslet/storage/table_probe.py",
        "src/lenslet/storage/table_schema.py",
        "src/lenslet/web/og.py",
        "src/lenslet/web/sync_events.py",
        "src/lenslet/web/sync_labels.py",
        "src/lenslet/web/sync_presence.py",
        "server_runtime.py",
        "server_sync.py",
        "table_facade.py",
        "table_paths.py",
        "table_media.py",
        "table_index_assembly.py",
        "src/lenslet/web/sync.py",
        "_file_response",
        "_thumb_response_async",
    ]

    assert [reference for reference in removed_references if reference in docs] == []


def test_documented_optional_extras_match_runtime_install_messages() -> None:
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    quickstart = (REPO_ROOT / "QUICKSTART_API.md").read_text(encoding="utf-8")
    cli_browse = (REPO_ROOT / "src" / "lenslet" / "cli" / "browse.py").read_text(encoding="utf-8")
    embedder = (REPO_ROOT / "src" / "lenslet" / "embeddings" / "embedder.py").read_text(
        encoding="utf-8"
    )

    assert "remote = [" in pyproject
    assert '"unibox>=0.12"' in pyproject
    assert "embed = [" in pyproject
    assert '"torch>=2"' in pyproject
    assert '"torchvision>=0.17"' in pyproject

    assert 'pip install "lenslet[remote]"' in readme
    assert 'pip install "lenslet[remote]"' in quickstart
    assert 'pip install "lenslet[remote]"' in cli_browse
    assert 'pip install "lenslet[embed]"' in readme
    assert 'pip install "lenslet[embed]"' in embedder


def test_readme_embedding_search_example_matches_request_contract() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    section = readme.split("### Embedding Similarity Search", maxsplit=1)[1]
    raw_payload = re.search(r"-d '([^']+)'", section)
    vector_request = re.search(r"request = (\{[^\n]+\})", section)

    assert raw_payload is not None
    assert vector_request is not None
    assert "query_path" not in section
    assert "query_vector_b64" not in section
    assert "query.vector_b64" in section

    payload = json.loads(raw_payload.group(1))
    request = EmbeddingSearchRequest.model_validate(payload)
    assert request.query.kind == "path"

    assert '"kind": "vector"' in vector_request.group(1)
    assert '"vector_b64": payload' in vector_request.group(1)
    vector_request_model = EmbeddingSearchRequest.model_validate(
        {"embedding": "clip", "query": {"kind": "vector", "vector_b64": "AAAA"}}
    )
    assert vector_request_model.query.kind == "vector"


def test_quickstart_uses_current_launch_options_api() -> None:
    quickstart = (REPO_ROOT / "QUICKSTART_API.md").read_text(encoding="utf-8")

    assert "lenslet.LaunchOptions(" in quickstart
    assert "lenslet.launch(datasets, blocking=" not in quickstart
    assert "lenslet.launch(datasets, port=" not in quickstart


def test_development_documents_browser_harness_churn_gate() -> None:
    development = (REPO_ROOT / "DEVELOPMENT.md").read_text(encoding="utf-8")

    assert "Browser Harness Change Gate" in development
    assert "scripts/browser/" in development
    assert "root cause" in development
    assert "expected open-issue reduction" in development
    assert "helper-only churn" in development


def test_development_documents_skip_debt_gate() -> None:
    development = (REPO_ROOT / "DEVELOPMENT.md").read_text(encoding="utf-8")

    assert "Skip Debt Gate" in development
    assert "permanent skip" in development
    assert "wontfix" in development
    assert "desloppify plan queue --include-skipped" in development
    assert "distort prioritization" in development


def test_quickstart_local_links_reference_existing_paths() -> None:
    quickstart = (REPO_ROOT / "QUICKSTART_API.md").read_text(encoding="utf-8")
    missing: list[str] = []

    for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", quickstart):
        if target.startswith(("http://", "https://", "#")):
            continue
        path = target.split("#", 1)[0]
        if path and not (REPO_ROOT / path).exists():
            missing.append(target)

    assert missing == []
