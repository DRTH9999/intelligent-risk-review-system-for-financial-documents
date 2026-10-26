"""审核规则、费用标准与市场价参考数据维护接口。"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, require_roles
from app.models import MarketPriceReference, ReviewRule, User
from app.schemas import RuleIn, RuleUpdate, MarketPriceInput
from app.services.audit import log_action
from app.services.rules import DEFAULT_RULE_DEFINITIONS, default_config
from app.utils import dump_json, iso, load_json
from app.services.rule_config import validate_rule_config

router = APIRouter(prefix="/api/v1", tags=["规则配置"])


def _rule_to_dict(rule: ReviewRule) -> dict:
    return {
        "id": rule.id,
        "rule_code": rule.rule_code,
        "rule_name": rule.rule_name,
        "rule_type": rule.rule_type,
        "document_type": rule.document_type,
        "config": load_json(rule.config_json, {}),
        "severity": rule.severity,
        "status": rule.status,
        "updated_by": rule.updated_by,
        "updated_at": iso(rule.updated_at),
    }


@router.get("/rules")
def list_rules(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict]:
    rules = db.execute(select(ReviewRule).order_by(ReviewRule.id)).scalars().all()
    existing = {rule.rule_code for rule in rules}
    result = [_rule_to_dict(rule) for rule in rules]
    for definition in DEFAULT_RULE_DEFINITIONS:
        if definition["rule_code"] not in existing:
            result.append(
                {
                    "id": None,
                    "rule_code": definition["rule_code"],
                    "rule_name": definition["rule_name"],
                    "rule_type": definition["rule_type"],
                    "document_type": None,
                    "config": default_config(definition["rule_code"]),
                    "severity": definition["severity"],
                    "status": "active",
                    "updated_by": None,
                    "updated_at": None,
                }
            )
    return result


@router.post("/rules")
def create_rule(payload: RuleIn, user: User = Depends(require_roles("finance", "admin")), db: Session = Depends(get_db)) -> dict:
    validate_rule_config(payload.rule_code, payload.config)
    exists = db.execute(select(ReviewRule).where(ReviewRule.rule_code == payload.rule_code)).scalars().first()
    if exists:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="规则编码已存在")
    rule = ReviewRule(
        rule_code=payload.rule_code,
        rule_name=payload.rule_name,
        rule_type=payload.rule_type,
        document_type=payload.document_type,
        config_json=dump_json(payload.config),
        severity=payload.severity,
        status=payload.status,
        updated_by=user.id,
    )
    db.add(rule)
    db.flush()
    log_action(db, user.id, "rule.create", "review_rule", rule.id, {"rule_code": rule.rule_code, "config": payload.config})
    db.commit()
    db.refresh(rule)
    return _rule_to_dict(rule)


@router.patch("/rules/{rule_id}")
def update_rule(rule_id: int, payload: RuleUpdate, user: User = Depends(require_roles("finance", "admin")), db: Session = Depends(get_db)) -> dict:
    rule = db.get(ReviewRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="规则不存在")
    data = payload.model_dump(exclude_unset=True)
    config = data.pop("config", None)
    before = load_json(rule.config_json, {})
    validate_rule_config(rule.rule_code, config if config is not None else before)
    before_state = _rule_to_dict(rule)
    for key, value in data.items():
        if value is not None:
            setattr(rule, key, value)
    if config is not None:
        rule.config_json = dump_json(config)
    rule.updated_by = user.id
    log_action(
        db,
        user.id,
        "rule.update",
        "review_rule",
        rule.id,
        {"rule_code": rule.rule_code, "before": before_state, "after": _rule_to_dict(rule)},
    )
    db.commit()
    db.refresh(rule)
    return _rule_to_dict(rule)


@router.get("/market-prices")
def list_market_prices(
    keyword: str | None = None,
    region: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    query = select(MarketPriceReference).order_by(MarketPriceReference.id.desc())
    if keyword:
        query = query.where(MarketPriceReference.item_name.like(f"%{keyword}%"))
    if region:
        query = query.where(MarketPriceReference.region == region)
    rows = db.execute(query).scalars().all()
    return [
        {
            "id": row.id,
            "item_name": row.item_name,
            "specification": row.specification,
            "region": row.region,
            "price_min": float(row.price_min),
            "price_max": float(row.price_max),
            "currency": row.currency,
            "source_name": row.source_name,
            "effective_date": row.effective_date.isoformat() if row.effective_date else None,
        }
        for row in rows
    ]


@router.post("/market-prices")
def create_market_price(
    payload: dict,
    user: User = Depends(require_roles("finance", "admin")),
    db: Session = Depends(get_db),
) -> dict:
    payload = MarketPriceInput.model_validate(payload).model_dump(mode='json')
    if not payload.get("item_name"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="商品/服务名称不能为空")
    reference = MarketPriceReference(
        item_name=payload["item_name"],
        specification=payload.get("specification"),
        region=payload.get("region"),
        price_min=payload.get("price_min") or 0,
        price_max=payload.get("price_max") or 0,
        currency=payload.get("currency") or "CNY",
        source_name=payload.get("source_name"),
        effective_date=date.fromisoformat(payload["effective_date"]) if payload.get("effective_date") else date.today(),
    )
    db.add(reference)
    log_action(db, user.id, "market_price.create", "market_price", None, {"item_name": reference.item_name})
    db.commit()
    db.refresh(reference)
    return {
        "id": reference.id,
        "item_name": reference.item_name,
        "specification": reference.specification,
        "region": reference.region,
        "price_min": float(reference.price_min),
        "price_max": float(reference.price_max),
        "currency": reference.currency,
        "source_name": reference.source_name,
        "effective_date": reference.effective_date.isoformat() if reference.effective_date else None,
    }


@router.patch("/market-prices/{price_id}")
def update_market_price(
    price_id: int,
    payload: dict,
    user: User = Depends(require_roles("finance", "admin")),
    db: Session = Depends(get_db),
) -> dict:
    reference = db.get(MarketPriceReference, price_id)
    if reference is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="市场价记录不存在")
    merged = {key:getattr(reference,key) for key in MarketPriceInput.model_fields}
    merged.update(payload)
    payload = MarketPriceInput.model_validate(merged).model_dump(mode='json')
    for field in ("item_name", "specification", "region", "price_min", "price_max", "currency", "source_name"):
        if field in payload and payload[field] is not None:
            setattr(reference, field, payload[field])
    if payload.get("effective_date"):
        reference.effective_date = date.fromisoformat(payload["effective_date"])
    log_action(db, user.id, "market_price.update", "market_price", reference.id, payload)
    db.commit()
    return {
        "id": reference.id,
        "item_name": reference.item_name,
        "price_min": float(reference.price_min),
        "price_max": float(reference.price_max),
        "region": reference.region,
        "source_name": reference.source_name,
        "effective_date": reference.effective_date.isoformat() if reference.effective_date else None,
    }
