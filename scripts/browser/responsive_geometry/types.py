from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

ScenarioRunner = Callable[[Any, str, float], dict[str, Any]]


@dataclass(frozen=True)
class Scenario:
    name: str
    width: int
    height: int
    storage: dict[str, str]
    open_mobile_search: bool = False
    has_touch: bool = False
    select_first: bool = False
    assert_inspector: bool = False


@dataclass(frozen=True)
class BrowserScenario:
    name: str
    width: int
    height: int
    runner: ScenarioRunner
    has_touch: bool = False
