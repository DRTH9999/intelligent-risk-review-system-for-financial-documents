"""规则配置入口校验：未知规则和无效参数不能进入运行中的规则引擎。"""
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException
from app.services.rules import DEFAULT_RULE_DEFINITIONS, default_config


def validate_rule_config(code, config):
    if code not in {row['rule_code'] for row in DEFAULT_RULE_DEFINITIONS}:
        raise HTTPException(422, '此规则编码没有对应的执行逻辑，请使用已登记规则')
    if not isinstance(config, dict) or set(config) - set(default_config(code)):
        raise HTTPException(422, '规则配置包含不支持的字段')
    def validate(values):
        for key,value in values.items():
            if isinstance(value, dict):
                validate(value)
            elif key in {'level','account_mismatch_level'}:
                if value not in {'low','medium','high'}: raise ValueError('风险等级必须为low、medium或high')
            elif key == 'company_name':
                if not isinstance(value,str) or not value.strip(): raise ValueError('公司名称不能为空')
            else:
                number = Decimal(str(value))
                if not number.is_finite() or number < 0 or number > Decimal('999999999999'):
                    raise ValueError('阈值必须为有限的非负数')
                if key.endswith('_days') or key.endswith('_count'):
                    if number < 1 or number != int(number): raise ValueError('天数和笔数必须为正整数')
                if key == 'min_confidence' and number > 1: raise ValueError('置信度必须在0到1之间')
    try:
        validate(config)
        merged = default_config(code) | config
        if 'medium_pct' in merged and Decimal(str(merged['high_pct'])) < Decimal(str(merged['medium_pct'])):
            raise ValueError('高风险阈值不能小于中风险阈值')
    except (ValueError, TypeError, InvalidOperation) as exc:
        raise HTTPException(422, f'规则配置无效：{exc}') from exc
