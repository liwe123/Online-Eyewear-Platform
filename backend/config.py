"""兼容层模块。

历史版本曾直接从 `backend.config` 导入数据库对象和配置项；
当前项目已经统一迁移到 `backend.settings` 与 `backend.models`，
这里保留同名导出以避免旧代码和旧测试失效。
"""
try:  # 支持包导入（gunicorn）与脚本直接运行两种方式
    from .models import db
    from .settings import settings
except ImportError:  # pragma: no cover
    from models import db
    from settings import settings

# 兼容旧版调用方的配置别名。
MODEL_API_URL: str = settings.MODEL_API_URL
BACKEND_PORT: int = settings.PORT

__all__ = ["db", "MODEL_API_URL", "BACKEND_PORT"]
