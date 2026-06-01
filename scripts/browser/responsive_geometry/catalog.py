from __future__ import annotations

from scripts.browser.responsive_geometry.fixtures import scenario_storage
from scripts.browser.responsive_geometry.types import Scenario


def layout_scenario_catalog() -> list[Scenario]:
    return [
        Scenario("desktop-open-oversized", 1440, 900, scenario_storage()),
        Scenario("phone-open-oversized", 320, 700, scenario_storage(), has_touch=True),
        Scenario("phone-toolbar-360", 360, 700, scenario_storage(), has_touch=True),
        Scenario("phone-toolbar-390", 390, 700, scenario_storage(), has_touch=True),
        Scenario(
            "phone-search-open-320",
            320,
            700,
            scenario_storage(),
            open_mobile_search=True,
            has_touch=True,
        ),
        Scenario(
            "narrow-search-open-640",
            640,
            760,
            scenario_storage(),
            open_mobile_search=True,
            has_touch=True,
        ),
        Scenario(
            "narrow-search-open-760",
            760,
            760,
            scenario_storage(),
            open_mobile_search=True,
        ),
        Scenario(
            "narrow-search-open-900",
            900,
            760,
            scenario_storage(),
            open_mobile_search=True,
        ),
        Scenario(
            "short-search-open-760",
            760,
            430,
            scenario_storage(),
            open_mobile_search=True,
        ),
        Scenario(
            "inspector-phone-suppressed-480",
            480,
            760,
            scenario_storage(),
            select_first=True,
            assert_inspector=True,
            has_touch=True,
        ),
        Scenario(
            "inspector-short-narrow-760",
            760,
            430,
            scenario_storage(),
            select_first=True,
            assert_inspector=True,
        ),
        Scenario(
            "inspector-short-tablet-1024",
            1024,
            480,
            scenario_storage(),
            select_first=True,
            assert_inspector=True,
        ),
        Scenario(
            "inspector-allowed-900",
            900,
            760,
            scenario_storage(),
            select_first=True,
            assert_inspector=True,
        ),
    ]
