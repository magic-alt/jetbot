from __future__ import annotations

import pytest


@pytest.fixture()
def golden_cases() -> list[dict]:
    """Return a list of golden test case dicts for evaluation.

    Each case has:
      - name: human-readable test case name
      - pages: list of Page-compatible dicts (page_number, text)
      - expected_statements: dict of statement_type -> expected totals dict
      - expected_note_types: list of expected note_type strings
      - expected_signal_categories: list of expected signal category strings
    """
    return [
        # ----------------------------------------------------------------
        # Case 1: Simple balance sheet + income + cashflow in Chinese
        # ----------------------------------------------------------------
        {
            "name": "chinese_three_statements",
            "pages": [
                {
                    "page_number": 1,
                    "text": (
                        "一、合并资产负债表\n"
                        "资产负债表\n"
                        "项目    本期金额    上期金额\n"
                        "流动资产:\n"
                        "货币资金    500,000    450,000\n"
                        "应收账款    200,000    180,000\n"
                        "存货    150,000    120,000\n"
                        "流动资产合计    850,000    750,000\n"
                        "非流动资产合计    650,000    600,000\n"
                        "资产总计    1,500,000    1,350,000\n"
                        "流动负债合计    400,000    350,000\n"
                        "非流动负债合计    200,000    200,000\n"
                        "负债合计    600,000    550,000\n"
                        "所有者权益合计    900,000    800,000\n"
                    ),
                },
                {
                    "page_number": 2,
                    "text": (
                        "二、合并利润表\n"
                        "利润表\n"
                        "项目    本期金额    上期金额\n"
                        "营业收入    2,000,000    1,800,000\n"
                        "营业成本    1,400,000    1,300,000\n"
                        "毛利润    600,000    500,000\n"
                        "营业利润    300,000    250,000\n"
                        "净利润    200,000    180,000\n"
                    ),
                },
                {
                    "page_number": 3,
                    "text": (
                        "三、合并现金流量表\n"
                        "现金流量表\n"
                        "项目    本期金额    上期金额\n"
                        "经营活动产生的现金流量净额    250,000    220,000\n"
                        "投资活动产生的现金流量净额    (100,000)    (80,000)\n"
                        "筹资活动产生的现金流量净额    (50,000)    (40,000)\n"
                        "现金及现金等价物净增加额    100,000    100,000\n"
                    ),
                },
            ],
            "expected_statements": {
                "balance": {"total_assets": 1_500_000, "total_liabilities": 600_000, "total_equity": 900_000},
                "income": {"revenue": 2_000_000, "net_income": 200_000},
                "cashflow": {},
            },
            "expected_note_types": ["other"],
            "expected_signal_categories": [],
        },
        # ----------------------------------------------------------------
        # Case 2: English financial statements with all 3 types
        # ----------------------------------------------------------------
        {
            "name": "english_full_statements",
            "pages": [
                {
                    "page_number": 1,
                    "text": (
                        "I. Consolidated Balance Sheet\n"
                        "Statement of Financial Position\n"
                        "Item    Current Period    Prior Period\n"
                        "Cash and equivalents    300,000    280,000\n"
                        "Accounts receivable    150,000    140,000\n"
                        "Total current assets    500,000    460,000\n"
                        "Total non-current assets    400,000    380,000\n"
                        "Total Assets    900,000    840,000\n"
                        "Total current liabilities    200,000    190,000\n"
                        "Total non-current liabilities    100,000    100,000\n"
                        "Total Liabilities    300,000    290,000\n"
                        "Total Equity    600,000    550,000\n"
                    ),
                },
                {
                    "page_number": 2,
                    "text": (
                        "II. Consolidated Income Statement\n"
                        "Statement of Operations\n"
                        "Revenue    1,200,000    1,100,000\n"
                        "Cost of goods sold    800,000    750,000\n"
                        "Gross Profit    400,000    350,000\n"
                        "Operating expenses    200,000    180,000\n"
                        "Operating income    200,000    170,000\n"
                        "Net Income    150,000    130,000\n"
                    ),
                },
                {
                    "page_number": 3,
                    "text": (
                        "III. Consolidated Statement of Cash Flows\n"
                        "Cash flow from operations    180,000    160,000\n"
                        "Cash flow from investing    (60,000)    (50,000)\n"
                        "Cash flow from financing    (30,000)    (20,000)\n"
                        "Net change in cash    90,000    90,000\n"
                    ),
                },
                {
                    "page_number": 4,
                    "text": (
                        "IV. Notes to Financial Statements\n"
                        "Accounting Policy: The company follows IFRS standards for revenue recognition.\n"
                        "Related Party Transactions: The company entered into transactions with "
                        "its subsidiary totaling 50,000.\n"
                        "Segment Information: The company operates in two segments: domestic and "
                        "international.\n"
                    ),
                },
            ],
            "expected_statements": {
                "balance": {"total_assets": 900_000, "total_liabilities": 300_000, "total_equity": 600_000},
                "income": {"revenue": 1_200_000, "net_income": 150_000},
                "cashflow": {},
            },
            "expected_note_types": ["accounting_policy", "related_party", "segment"],
            "expected_signal_categories": [],
        },
        # ----------------------------------------------------------------
        # Case 3: Edge case -- only income statement available
        # ----------------------------------------------------------------
        {
            "name": "income_only",
            "pages": [
                {
                    "page_number": 1,
                    "text": (
                        "Annual Report Summary\n"
                        "Income Statement\n"
                        "Revenue    500,000    450,000\n"
                        "Cost of goods sold    300,000    280,000\n"
                        "Gross Profit    200,000    170,000\n"
                        "Operating expenses    100,000    90,000\n"
                        "Net Income    80,000    65,000\n"
                    ),
                },
                {
                    "page_number": 2,
                    "text": (
                        "Management Discussion\n"
                        "The company achieved solid growth driven by expanding market share "
                        "and improved operational efficiency. Revenue grew 11% year-over-year.\n"
                    ),
                },
            ],
            "expected_statements": {
                "income": {"revenue": 500_000, "net_income": 80_000},
            },
            "expected_note_types": ["other"],
            "expected_signal_categories": [],
        },
        # ----------------------------------------------------------------
        # Case 4: Balance equation fails (assets != liabilities + equity)
        # ----------------------------------------------------------------
        {
            "name": "balance_equation_fail",
            "pages": [
                {
                    "page_number": 1,
                    "text": (
                        "一、资产负债表\n"
                        "资产负债表\n"
                        "项目    本期金额    上期金额\n"
                        "货币资金    100,000    90,000\n"
                        "应收账款    80,000    70,000\n"
                        "资产总计    500,000    400,000\n"
                        "负债合计    200,000    180,000\n"
                        "所有者权益合计    250,000    200,000\n"
                    ),
                },
                {
                    "page_number": 2,
                    "text": (
                        "二、利润表\n"
                        "利润表\n"
                        "营业收入    800,000    700,000\n"
                        "营业成本    600,000    550,000\n"
                        "毛利润    200,000    150,000\n"
                        "净利润    100,000    80,000\n"
                    ),
                },
                {
                    "page_number": 3,
                    "text": (
                        "三、现金流量表\n"
                        "现金流量表\n"
                        "经营活动产生的现金流量净额    120,000    100,000\n"
                        "投资活动产生的现金流量净额    (40,000)    (30,000)\n"
                        "筹资活动产生的现金流量净额    (20,000)    (15,000)\n"
                    ),
                },
            ],
            "expected_statements": {
                "balance": {"total_assets": 500_000, "total_liabilities": 200_000, "total_equity": 250_000},
                "income": {"revenue": 800_000, "net_income": 100_000},
                "cashflow": {},
            },
            "expected_note_types": ["other"],
            "expected_signal_categories": ["disclosure_inconsistency"],
        },
        # ----------------------------------------------------------------
        # Case 5: Audit opinion and risk disclosures
        # ----------------------------------------------------------------
        {
            "name": "audit_opinion_and_risks",
            "pages": [
                {
                    "page_number": 1,
                    "text": (
                        "一、资产负债表\n"
                        "资产负债表\n"
                        "资产总计    1,000,000    900,000\n"
                        "负债合计    400,000    350,000\n"
                        "所有者权益合计    600,000    550,000\n"
                    ),
                },
                {
                    "page_number": 2,
                    "text": (
                        "二、利润表\n"
                        "利润表\n"
                        "营业收入    600,000    550,000\n"
                        "营业成本    400,000    380,000\n"
                        "毛利润    200,000    170,000\n"
                        "净利润    120,000    100,000\n"
                    ),
                },
                {
                    "page_number": 3,
                    "text": (
                        "三、现金流量表\n"
                        "现金流量表\n"
                        "经营活动产生的现金流量净额    (50,000)    80,000\n"
                        "投资活动产生的现金流量净额    (30,000)    (20,000)\n"
                        "筹资活动产生的现金流量净额    100,000    (10,000)\n"
                    ),
                },
                {
                    "page_number": 4,
                    "text": (
                        "四、审计报告\n"
                        "审计意见：我们对ABC公司的财务报表进行了审计。\n"
                        "审计师出具了保留意见的审计报告。\n"
                        "强调事项：公司存在重大不确定性，可能影响持续经营能力。\n"
                        "或有负债：公司面临多项未决诉讼，涉及金额约50,000,000元。\n"
                        "关联方交易：公司与母公司之间存在大额资金往来。\n"
                    ),
                },
                {
                    "page_number": 5,
                    "text": (
                        "五、风险披露\n"
                        "资产减值：公司对商誉进行了减值测试，确认减值损失10,000,000元。\n"
                        "经营风险：公司所处行业竞争加剧，可能对未来盈利造成不利影响。\n"
                        "合规风险：公司部分业务可能受到新出台监管政策的影响。\n"
                    ),
                },
            ],
            "expected_statements": {
                "balance": {"total_assets": 1_000_000, "total_liabilities": 400_000, "total_equity": 600_000},
                "income": {"revenue": 600_000, "net_income": 120_000},
                "cashflow": {},
            },
            "expected_note_types": ["audit_opinion", "contingency", "related_party", "impairment"],
            "expected_signal_categories": ["audit_governance", "cash_vs_profit"],
        },
    ]
