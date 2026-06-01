from __future__ import annotations

import importlib
import inspect
from importlib.metadata import version
from pathlib import Path
import sys

import lenslet
import lenslet.api as api
import pytest


def test_launch_rejects_empty_payload() -> None:
    with pytest.raises(ValueError, match="non-empty dict"):
        api.launch({})


def test_launch_table_rejects_non_table_payload() -> None:
    with pytest.raises(ValueError, match="table-like object"):
        api.launch_table(object())


def test_launch_table_rejects_non_callable_table_protocol_members() -> None:
    class _NonCallablePyDict:
        to_pydict = {"path": ["gallery/a.jpg"]}

    class _NonCallableToDict:
        columns = ["path"]
        to_dict = {"path": ["gallery/a.jpg"]}

        def __getitem__(self, column: str) -> object:
            return object()

    class _NonCallableGetItem:
        columns = ["path"]
        __getitem__ = object()

        def to_dict(self) -> dict[str, list[str]]:
            return {"path": ["gallery/a.jpg"]}

    for table in (_NonCallablePyDict(), _NonCallableToDict(), _NonCallableGetItem()):
        with pytest.raises(ValueError, match="table-like object"):
            api.launch_table(table)  # type: ignore[arg-type]


def test_table_input_contract_accepts_list_of_dict_rows() -> None:
    rows = [{"path": "gallery/a.jpg", "source": "/tmp/a.jpg"}]

    assert api.is_table_input(rows) is True
    assert api.table_input_length(rows) == 1


def test_top_level_programmatic_exports_are_explicit() -> None:
    assert hasattr(lenslet, "LaunchOptions")
    assert hasattr(lenslet, "TableLaunchOptions")
    assert hasattr(lenslet, "launch")
    assert hasattr(lenslet, "launch_table")
    assert not hasattr(lenslet, "launch_datasets")
    assert "launch_datasets" not in lenslet.__all__
    assert "LaunchOptions" in lenslet.__all__
    assert "TableLaunchOptions" in lenslet.__all__


def test_package_version_matches_build_metadata() -> None:
    assert lenslet.__version__ == version("lenslet")


def test_import_lenslet_defers_version_resolution(monkeypatch) -> None:
    calls: list[str] = []

    def _version(name: str) -> str:
        calls.append(name)
        return "9.9.9-lazy"

    def _unexpected_read_text(self: Path, *_args, **_kwargs) -> str:
        raise AssertionError(f"pyproject should not be read during package import: {self}")

    monkeypatch.delitem(sys.modules, "lenslet", raising=False)
    monkeypatch.delitem(sys.modules, "lenslet.version", raising=False)
    monkeypatch.setattr("importlib.metadata.version", _version)
    monkeypatch.setattr(Path, "read_text", _unexpected_read_text)

    imported = importlib.import_module("lenslet")

    assert calls == []
    assert "__version__" in imported.__all__
    assert imported.__version__ == "9.9.9-lazy"
    assert calls == ["lenslet"]


def test_launch_signature_is_dataset_only() -> None:
    signature = inspect.signature(lenslet.launch)
    assert list(signature.parameters) == [
        "datasets",
        "options",
    ]


def test_launch_table_signature_exposes_table_specific_options() -> None:
    signature = inspect.signature(lenslet.launch_table)
    assert list(signature.parameters) == [
        "table",
        "options",
    ]


def test_launch_option_defaults_match_public_server_defaults() -> None:
    options = lenslet.LaunchOptions()
    assert options.blocking is False
    assert options.host == "127.0.0.1"
    assert options.port == 7070
    assert options.thumb_size == 256
    assert options.thumb_quality == 70
    assert options.show_source is True
    assert options.verbose is False


def test_table_launch_options_extend_shared_defaults() -> None:
    options = lenslet.TableLaunchOptions(
        source_column="source",
        path_column="display_path",
        base_dir="/data",
    )
    assert options.port == 7070
    assert options.source_column == "source"
    assert options.path_column == "display_path"
    assert options.base_dir == "/data"
