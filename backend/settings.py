"""统一配置模块：基于 pydantic-settings，环境变量无前缀或 BACKEND_ 前缀均可生效。"""
from pathlib import Path
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 项目根目录（backend/ 的上一级），用于解析默认数据库与数据目录
BASE_DIR: Path = Path(__file__).resolve().parent.parent
DATA_DIR: Path = BASE_DIR / "data"


class Settings(BaseSettings):
    """后端服务配置。环境变量示例：`MODEL_API_URL=...` 或 `BACKEND_MODEL_API_URL=...`。"""

    model_config = SettingsConfigDict(
        env_prefix="BACKEND_",
        env_file=".env",
        extra="ignore",
    )

    MODEL_API_URL: str = "http://localhost:8000"
    PORT: int = 5000
    DATABASE_URL: str = f"sqlite:///{(DATA_DIR / 'backend.db').as_posix()}"
    SECRET_KEY: str = "dev-secret-do-not-use-in-production-change-me"
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "admin123"
    CORS_ORIGINS: str = "http://127.0.0.1:5500,http://localhost:5500"
    LOG_LEVEL: str = "INFO"

    @property
    def cors_origin_list(self) -> List[str]:
        """将逗号分隔的 CORS_ORIGINS 拆分为列表。"""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


def _load_settings() -> Settings:
    """加载配置：优先读取带 BACKEND_ 前缀的变量，无前缀变量作为兜底。"""
    import os

    # pydantic-settings 只认 env_prefix，这里把无前缀的同名变量桥接进来
    for key in Settings.model_fields:
        prefixed = f"BACKEND_{key}"
        if key in os.environ and prefixed not in os.environ:
            os.environ[prefixed] = os.environ[key]
    return Settings()


settings: Settings = _load_settings()
