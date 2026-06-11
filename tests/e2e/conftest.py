"""E2E proxy tests run with no Postgres (the org_session seam is faked per
test). Budget enforcement and alerting genuinely need the database, so neutralize
them here; budget behavior is covered by its own tests against a real session.
"""

from __future__ import annotations

from typing import Any

import pytest


@pytest.fixture(autouse=True)
def _no_budget_io(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _noop(*args: Any, **kwargs: Any) -> None:
        return None

    monkeypatch.setattr("replay.budget.enforce", _noop)
    monkeypatch.setattr("replay.budget.evaluate_and_alert", _noop)
