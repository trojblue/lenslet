from __future__ import annotations

import inspect

import lenslet
import lenslet.api as api
import pytest


def test_launch_rejects_empty_payload() -> None:
    with pytest.raises(ValueError, match="non-empty dict"):
        api.launch({})


def test_launch_table_rejects_non_table_payload() -> None:
    with pytest.raises(ValueError, match="table-like object"):
        api.launch_table(object())


def test_top_level_programmatic_exports_are_explicit() -> None:
    assert hasattr(lenslet, "launch")
    assert hasattr(lenslet, "launch_table")
    assert not hasattr(lenslet, "launch_datasets")
    assert "launch_datasets" not in lenslet.__all__


def test_launch_signature_is_dataset_only() -> None:
    signature = inspect.signature(lenslet.launch)
    assert list(signature.parameters) == [
        "datasets",
        "blocking",
        "port",
        "host",
        "thumb_size",
        "thumb_quality",
        "show_source",
        "verbose",
    ]


def test_launch_table_signature_exposes_table_specific_options() -> None:
    signature = inspect.signature(lenslet.launch_table)
    assert list(signature.parameters) == [
        "table",
        "blocking",
        "port",
        "host",
        "thumb_size",
        "thumb_quality",
        "show_source",
        "verbose",
        "source_column",
        "base_dir",
    ]
