"""兼容层：保留旧版 config 模块的导出，内部统一委托 settings/models。

新代码请直接使用 backend.settings.settings 与 backend.models.db。
"""
try:  # 支持包导入（gunicorn）与脚本直接运行两种方式
    from .models import db
    from .settings import settings
except ImportError:  # pragma: no cover
    from models import db
    from settings import settings

# 旧代码兼容导出
MODEL_API_URL: str = settings.MODEL_API_URL
BACKEND_PORT: int = settings.PORT

__all__ = ["db", "MODEL_API_URL", "BACKEND_PORT"]
