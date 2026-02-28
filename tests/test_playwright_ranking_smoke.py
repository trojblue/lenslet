from __future__ import annotations

import importlib.util
import socket
import sys
from pathlib import Path
from types import ModuleType

import pytest


def _load_smoke_module() -> ModuleType:
    module_path = Path(__file__).resolve().parents[1] / "scripts" / "playwright_ranking_smoke.py"
    spec = importlib.util.spec_from_file_location("playwright_ranking_smoke", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load playwright_ranking_smoke module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_build_fixture_dataset_writes_expected_shape(tmp_path: Path) -> None:
    smoke = _load_smoke_module()
    dataset_path = smoke.build_fixture_dataset(tmp_path)

    assert dataset_path.exists()
    payload = smoke.json.loads(dataset_path.read_text(encoding="utf-8"))
    assert isinstance(payload, list)
    assert len(payload) == 2
    assert payload[0]["instance_id"] == "one"
    assert payload[1]["instance_id"] == "two"

    image_paths = [
        tmp_path / rel_path
        for instance in payload
        for rel_path in instance["images"]
    ]
    assert all(path.exists() for path in image_paths)


def test_parse_instance_position_contract() -> None:
    smoke = _load_smoke_module()

    assert smoke.parse_instance_position("2 / 5") == (2, 5)
    with pytest.raises(smoke.SmokeFailure):
        smoke.parse_instance_position("bad-label")
    with pytest.raises(smoke.SmokeFailure):
        smoke.parse_instance_position("0 / 2")


def test_health_results_path_contract() -> None:
    smoke = _load_smoke_module()
    good = smoke.health_results_path({"results_path": "/tmp/out/results.jsonl"})
    assert good.name == "results.jsonl"

    with pytest.raises(smoke.SmokeFailure):
        smoke.health_results_path({})
    with pytest.raises(smoke.SmokeFailure):
        smoke.health_results_path({"results_path": ""})
    with pytest.raises(smoke.SmokeFailure):
        smoke.health_results_path({"results_path": None})


def test_choose_port_falls_back_when_preferred_is_occupied() -> None:
    smoke = _load_smoke_module()

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as occupied:
        occupied.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        occupied.bind(("127.0.0.1", 0))
        occupied.listen(1)
        busy_port = int(occupied.getsockname()[1])

        chosen = smoke.choose_port("127.0.0.1", busy_port)
        assert chosen != busy_port
        assert isinstance(chosen, int)
        assert chosen > 0


def test_parse_args_defaults() -> None:
    smoke = _load_smoke_module()
    args = smoke.parse_args([])

    assert args.dataset_json is None
    assert args.host == "127.0.0.1"
    assert args.port == 7071
    assert args.keep_fixture is False
