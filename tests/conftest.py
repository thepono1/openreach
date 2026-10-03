"""Guards against the exact hazard this project hit twice this session: a
test suite that silently clicks, types, or scrolls on whoever's real
desktop happens to be running pytest. CI runners are disposable, so the
full suite runs there by default (set OPENREACH_ALLOW_LIVE_INPUT=1, which
the CI workflow does). A developer's own machine is not disposable, so
locally the same tests are skipped unless explicitly opted in.
"""

from __future__ import annotations

import os

import pytest

LIVE_INPUT_ENV = "OPENREACH_ALLOW_LIVE_INPUT"


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if os.environ.get(LIVE_INPUT_ENV) == "1":
        return
    skip_live = pytest.mark.skip(
        reason=f"live input disabled locally; set {LIVE_INPUT_ENV}=1 to let this test "
        "click/type/scroll on the real desktop (CI sets this automatically)"
    )
    for item in items:
        if "live_input" in item.keywords:
            item.add_marker(skip_live)
