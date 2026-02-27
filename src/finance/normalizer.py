from __future__ import annotations

NORMALIZATION_MAP = {
    "营业收入": "revenue",
    "主营业务收入": "revenue",
    "收入": "revenue",
    "营业成本": "cost_of_goods_sold",
    "毛利": "gross_profit",
    "净利润": "net_income",
    "归属于母公司所有者的净利润": "net_income",
    "资产总计": "total_assets",
    "负债合计": "total_liabilities",
    "所有者权益合计": "total_equity",
    "经营活动产生的现金流量净额": "operating_cf",
}


def normalize_account_name(raw_name: str) -> str:
    name = raw_name.strip()
    return NORMALIZATION_MAP.get(name, name)
