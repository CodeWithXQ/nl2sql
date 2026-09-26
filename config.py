"""全局配置：路径、MySQL 连接、LLM 接入，均从环境变量 / .env 读取。"""
from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
TESTSET_DIR = DATA_DIR / "testset"


def load_env(path: Path | None = None) -> None:
    env_path = path or (PROJECT_ROOT / ".env")
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def get_mysql_config() -> dict:
    load_env()
    return {
        "host": os.environ.get("MYSQL_HOST", "localhost"),
        "port": int(os.environ.get("MYSQL_PORT", "3306")),
        "user": os.environ.get("MYSQL_USER", "root"),
        "password": os.environ.get("MYSQL_PASSWORD", ""),
        "charset": "utf8mb4",
        "database": os.environ.get("MYSQL_DATABASE", ""),
    }


def get_llm_config() -> dict:
    load_env()
    return {
        "base_url": os.environ.get("LLM_BASE_URL", "https://api.deepseek.com"),
        "api_key": os.environ.get("LLM_API_KEY", ""),
        "model": os.environ.get("LLM_MODEL", "deepseek-chat"),
        "timeout": int(os.environ.get("LLM_TIMEOUT", "60")),
        "temperature": float(os.environ.get("LLM_TEMPERATURE", "0.1")),
        "max_tokens": int(os.environ.get("LLM_MAX_TOKENS", "1024")),
    }
