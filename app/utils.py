"""通用工具函数。"""
from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any


def now() -> datetime:
    """系统统一使用本地时间（Asia/Shanghai 运行环境）。"""
    return datetime.now().replace(microsecond=0)


def today() -> date:
    return date.today()


def iso(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat(sep=" ") if isinstance(value, datetime) else value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def dump_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=iso)


def load_json(value: Any, default: Any = None) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def money(value: Any) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def pct(part: float, total: float) -> float:
    if not total:
        return 0.0
    return round(abs(part - total) / total * 100, 2)


def to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(str(value).replace(",", "").replace("¥", "").replace("￥", "").strip())
    except (TypeError, ValueError):
        return default


def parse_date(text: str | None) -> str | None:
    """尽量从文本中规范化日期为 YYYY-MM-DD。"""
    if not text:
        return None
    import re

    m = re.search(r"(\d{4})\s*[年\-/.]\s*(\d{1,2})\s*[月\-/.]\s*(\d{1,2})", text)
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return None


def money_text(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "¥0.00"
    if number < 0:
        return f"-¥{abs(number):,.2f}"
    return f"¥{number:,.2f}"
