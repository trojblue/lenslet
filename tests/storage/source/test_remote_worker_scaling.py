from __future__ import annotations

from lenslet.storage.table import TableStorage
from lenslet.storage.source.probe import effective_remote_workers


def test_effective_remote_workers_scales_with_cpu() -> None:
    assert effective_remote_workers(
        total=200,
        baseline_workers=TableStorage.REMOTE_DIM_WORKERS,
        max_workers=TableStorage.REMOTE_DIM_WORKERS_MAX,
        cpu_count=lambda: 80,
    ) == 80

    assert effective_remote_workers(
        total=200,
        baseline_workers=TableStorage.REMOTE_DIM_WORKERS,
        max_workers=TableStorage.REMOTE_DIM_WORKERS_MAX,
        cpu_count=lambda: 4,
    ) == TableStorage.REMOTE_DIM_WORKERS

    # Still respect both the max cap and the total work available.
    assert effective_remote_workers(
        total=50,
        baseline_workers=TableStorage.REMOTE_DIM_WORKERS,
        max_workers=TableStorage.REMOTE_DIM_WORKERS_MAX,
        cpu_count=lambda: 512,
    ) == 50
