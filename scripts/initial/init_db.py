"""数据库初始化脚本：建库 + Alembic 迁移。"""

import sys
from pathlib import Path

from loguru import logger

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from service.database.bootstrap import ensure_database_exists, verify_connection  # noqa: E402
from settings.config import get_settings  # noqa: E402


def main() -> None:
    settings = get_settings()
    logger.info("检查/创建数据库: {}", settings.pg_database)
    ensure_database_exists(settings)

    if not verify_connection():
        msg = "数据库连接失败"
        raise RuntimeError(msg)

    logger.info("执行 Alembic 迁移")
    alembic_cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    command.upgrade(alembic_cfg, "head")
    logger.info("迁移完成")


if __name__ == "__main__":
    main()
