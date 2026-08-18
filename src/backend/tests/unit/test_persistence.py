"""仓储工厂单元测试（不依赖数据库）。"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from service.persistence import get_repositories  # noqa: E402


def test_get_repositories_returns_all_domains() -> None:
    session = MagicMock()
    repos = get_repositories(session)
    assert repos.permission is not None
    assert repos.conversation is not None
    assert repos.workflow is not None
    assert repos.agent is not None
    assert repos.knowledge is not None
    assert repos.audit is not None
    assert repos.graph is not None
    assert repos.security is not None
    assert repos.observability is not None
    assert repos.notification is not None
