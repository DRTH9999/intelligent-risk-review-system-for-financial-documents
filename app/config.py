"""系统配置。所有路径均以项目根目录为基准。"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# 读取项目根目录的 .env（不存在时忽略）；已存在的进程环境变量优先级更高
load_dotenv(BASE_DIR / ".env", override=False)

DATA_DIR = Path(os.getenv("RISK_REVIEW_DATA_DIR", BASE_DIR / "data"))
STORAGE_DIR = Path(os.getenv("RISK_REVIEW_STORAGE_DIR", BASE_DIR / "storage"))
ATTACHMENT_DIR = STORAGE_DIR / "attachments"
STATIC_DIR = BASE_DIR / "app" / "static"
EXPORT_DIR = DATA_DIR / "exports"

for _dir in (DATA_DIR, STORAGE_DIR, ATTACHMENT_DIR, EXPORT_DIR):
    _dir.mkdir(parents=True, exist_ok=True)

DATABASE_URL = os.getenv("RISK_REVIEW_DATABASE_URL", f"sqlite:///{(DATA_DIR / 'risk_review.db').as_posix()}")

SECRET_KEY = os.getenv("RISK_REVIEW_SECRET_KEY", "risk-review-dev-secret-key-change-in-production")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("RISK_REVIEW_TOKEN_EXPIRE_MINUTES", "480"))

MAX_ATTACHMENT_SIZE = 15 * 1024 * 1024  # 15MB
ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}
ALLOWED_MIME_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/jpg",
    "application/octet-stream",
}

APP_NAME = "财务单据智能风险审核系统"
APP_VERSION = "1.1.0"
