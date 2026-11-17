from pathlib import Path

import pandas as pd


FILES = {
    "export": Path(r"D:\JMH\出口业务收汇情况表\外汇退税\数据源\2025-9~12出口明细.xlsx"),
    "purchase": Path(r"D:\JMH\出口业务收汇情况表\外汇退税\数据源\2025-9~12进货明细.xlsx"),
    "receipt": Path(r"D:\JMH\出口业务收汇情况表\外汇退税\数据源\外汇回款汇总表(9-12).xlsx"),
}


def report(name: str, frame: pd.DataFrame, candidates: list[list[str]]) -> None:
    print(f"\n{name}: rows={len(frame)}")
    for columns in candidates:
        keys = frame[columns].fillna("").astype(str).agg("|".join, axis=1)
        print(f"  {columns}: unique={keys.nunique()}, duplicate_rows={keys.duplicated(False).sum()}")


export = pd.read_excel(FILES["export"], sheet_name="Sheet1", dtype=object).dropna(how="all")
report(
    "export",
    export,
    [
        ["关联号"],
        ["申报年月", "申报批次", "序号", "关联号"],
        ["关联号", "出口发票号码", "出口货物报关单号", "出口商品代码"],
        ["申报年月", "申报批次", "序号", "关联号", "出口发票号码", "出口货物报关单号", "出口商品代码"],
    ],
)

purchase = pd.read_excel(FILES["purchase"], sheet_name="Sheet1", dtype=object).dropna(how="all")
purchase.columns = ["序号" if str(column).startswith("Unnamed: 2") else column for column in purchase.columns]
report(
    "purchase",
    purchase,
    [
        ["关联号"],
        ["申报年月", "申报批次", "序号", "关联号"],
        ["关联号", "进货凭证号", "出口商品代码", "供货方纳税号"],
        ["申报年月", "申报批次", "序号", "关联号", "进货凭证号", "出口商品代码", "供货方纳税号"],
    ],
)

receipt = pd.read_excel(FILES["receipt"], sheet_name="Sheet1", usecols=range(15), dtype=object)
receipt = receipt.dropna(subset=["合同编号", "报关单号"], how="all")
report(
    "receipt",
    receipt,
    [
        ["合同编号"],
        ["合同编号", "报关单号"],
        ["合同编号", "报关单号", "核心流水号"],
    ],
)
