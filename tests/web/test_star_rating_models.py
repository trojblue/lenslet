from __future__ import annotations

from collections.abc import Callable

import pytest
from pydantic import ValidationError

from lenslet.web.models import BrowseItemPayload, Sidecar, SidecarPatch
from lenslet.web.sidecars import apply_patch_to_sidecar


def _browse_item(star: object) -> BrowseItemPayload:
    return BrowseItemPayload(
        path="/sample.jpg",
        name="sample.jpg",
        mime="image/jpeg",
        width=8,
        height=6,
        size=123,
        star=star,
    )


@pytest.mark.parametrize(
    "factory",
    [
        _browse_item,
        lambda star: Sidecar(star=star),
        lambda star: SidecarPatch(set_star=star),
    ],
)
@pytest.mark.parametrize("star", [0, 1, 2, 3, 4, 5, None])
def test_star_rating_models_accept_frontend_contract(
    factory: Callable[[object], object],
    star: int | None,
) -> None:
    factory(star)


@pytest.mark.parametrize(
    "factory",
    [
        _browse_item,
        lambda star: Sidecar(star=star),
        lambda star: SidecarPatch(set_star=star),
    ],
)
@pytest.mark.parametrize("star", [-1, 6, True, False])
def test_star_rating_models_reject_values_outside_frontend_contract(
    factory: Callable[[object], object],
    star: object,
) -> None:
    with pytest.raises(ValidationError):
        factory(star)


def test_sidecar_patch_applies_validated_star_rating_values() -> None:
    sidecar = {"tags": [], "notes": "", "star": None, "version": 1}

    assert apply_patch_to_sidecar(sidecar, SidecarPatch(set_star=5)) is True
    assert sidecar["star"] == 5

    assert apply_patch_to_sidecar(sidecar, SidecarPatch(set_star=None)) is True
    assert sidecar["star"] is None
