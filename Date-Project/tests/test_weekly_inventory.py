from decimal import Decimal
from datetime import date, datetime
from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest
from openpyxl import load_workbook
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.services import weekly_inventory_sync_service as sync
from backend.services import weekly_inventory_export_service as export
from backend.repositories import weekly_inventory_repository as repo
from backend.api.v1 import weekly_inventory as api


def sample():
    inventory = [dict(wid=1, product_id=2, seller_id="a", sku="=SKU", product_total="10", purchase_price="1.234567",
                      product_valid_num="9", stock_age_list=[dict(name="0-29天", qty=10)],
                      third_inventory={"third_inventory_data": [dict(name="可用量", local=9, third=8, diff=1)]}),
                 dict(wid=1, product_id=2, seller_id="b", sku="=SKU", product_total="5", purchase_price="99",
                      product_valid_num="20", stock_age_list=[dict(name="0-29天", qty=5)])]
    bins = [dict(wid=1, whb_id=3, product_id=2, lockNum=1, validNum=3, whb_type=9),
            dict(wid=1, whb_id=4, product_id=2, lockNum=2, validNum=4)]
    return sync.normalize(inventory, bins, [dict(id=2, product_name="产品", model="X"*222)], date(2026,9,9), "batch", datetime.now())


def test_representative_whole_row_and_age_not_double_counted():
    headers, rows = export.build_rows(sample(), {1:"仓库"})
    row = dict(zip(headers, rows[0]))
    assert len(rows) == 1
    assert row["实际库存总量"] == 10
    assert row["可用量"] == 9  # not MAX(20) from a different seller
    assert row["0-29天"] == 10  # not sum(10+5)
    assert row["锁定量(仓位)"] == 3
    assert row["未锁定量(仓位)"] == 7
    assert row["库存金额"] == Decimal("12.345670")
    assert not any(label.startswith("第三方-") for label in headers)
    assert len(headers) == 26  # 25 static + 1 dynamic
    assert len(rows[0]) == len(headers)


@pytest.mark.parametrize('grams,kilograms', [
    (None, None), (Decimal('0'), Decimal('0')),
    (Decimal('1500'), Decimal('1.5')), (Decimal('1000'), Decimal('1')),
    (Decimal('25.5'), Decimal('0.0255')),
])
def test_only_exported_gross_weight_converts_to_kg(grams, kilograms):
    groups = sample()
    product = groups['products'][0]
    product.update(cg_product_gross_weight=grams, cg_product_net_weight=Decimal('900'),
                   cg_box_weight=Decimal('8.5'))
    headers, rows = export.build_rows(groups, {1: '仓库'})
    row = dict(zip(headers, rows[0]))
    assert '采购-产品毛重(G)' not in headers
    assert row['采购-产品毛重(KG)'] == kilograms
    assert row['采购-产品净重(G)'] == Decimal('900')
    assert row['采购-外箱实重(KG)'] == Decimal('8.5')
    assert product['cg_product_gross_weight'] == grams


def test_missing_is_not_zero():
    groups = sample()
    groups["inventory"] = groups["inventory"][:1]
    groups["inventory"][0]["product_bad_num"] = Decimal(0)
    groups["bins"] = []
    groups["age"] = []
    headers, rows = export.build_rows(groups,{1:"仓库"})
    row=dict(zip(headers,rows[0]))
    assert row["次品量"] == 0
    assert row["锁定量(仓位)"] is None
    assert row["采购-产品净重(G)"] is None


def test_xlsx_is_safe_and_archive_never_replaced(tmp_path):
    path=tmp_path/"中文.xlsx"
    metrics=export.write_export(sample(),{1:"仓库"},path)
    original=path.read_bytes()
    wb=load_workbook(path)
    assert wb.active["B2"].value == "=SKU"
    assert wb.active["B2"].data_type == "s"
    assert wb.active.max_column == metrics["column_count"]
    wb.close()
    with pytest.raises(FileExistsError):
        export.write_export(sample(),{1:"仓库"},path)
    assert path.read_bytes()==original
    assert not list(tmp_path.glob(".weekly-*"))


def test_xlsx_numeric_format_and_removed_columns(tmp_path):
    groups = sample()
    groups["inventory"][0]["product_bad_num"] = Decimal("0.000000")
    groups["products"][0].update(cg_product_length=Decimal("75.000000"),
                                cg_product_width=Decimal("25.500000"),
                                cg_product_height=Decimal("-2.000000"))
    path = tmp_path / "format.xlsx"
    export.write_export(groups, {1: "仓库"}, path)
    with_source = groups["inventory"][0]["third_inventory"]
    assert with_source["third_inventory_data"][0]["third"] == 8
    wb = load_workbook(path)
    try:
        sheet = wb.active
        cells = dict(zip([c.value for c in sheet[1]], sheet[2]))
        assert not any(name.startswith("第三方-") for name in cells)
        assert sheet.max_column == 26
        assert sheet.freeze_panes == "E2"
        for name, expected, fmt in [
            ("实际库存总量", 10, "0"), ("次品量", 0, "0"),
            ("采购-产品规格-长(CM)", 75, "0"),
            ("采购-产品规格-宽(CM)", 25.5, "0.0#####"),
            ("采购-产品规格-高(CM)", -2, "0"),
            ("采购单价", 1.234567, "0.0#####"),
            ("库存金额", 12.34567, "0.0#####"),
        ]:
            assert cells[name].value == expected
            assert cells[name].data_type == "n"
            assert cells[name].number_format == fmt
    finally:
        wb.close()


@pytest.mark.parametrize("value", ["NaN", "Infinity", "nonsense", True])
def test_invalid_numbers(value):
    with pytest.raises(ValueError): sync.number(value)


def test_duplicate_primary_key_rejected():
    with pytest.raises(ValueError):
        sync.unique([dict(id=1),dict(id=1)], ("id",))


def test_pagination_complete():
    client=MagicMock()
    client.post_signed_query_auth.side_effect=[dict(code=0,total=3,data=[{},{}]),dict(code=0,total=3,data=[{}])]
    assert len(sync.fetch_pages(client,"inventoryDetails",2)) == 3
    assert client.post_signed_query_auth.call_args.args[1]==dict(offset=2,length=2)


@pytest.mark.parametrize("responses", [
    [dict(code=0,total=3,data=[{}])],
    [dict(code=0,total=3,data=[{},{}]),dict(code=0,total=4,data=[{},{}])],
    [dict(code=0,data=[])], [dict(code=1,total=0,data=[])],
])
def test_incomplete_pages_rejected(responses):
    client=MagicMock(); client.post_signed_query_auth.side_effect=responses
    with pytest.raises(ValueError): sync.fetch_pages(client,"inventoryDetails",2)


def test_snapshot_transaction_rollback(monkeypatch):
    connection=MagicMock(); cursor=connection.cursor.return_value.__enter__.return_value
    cursor.executemany.side_effect=RuntimeError("insert failure")
    @contextmanager
    def connect(): yield connection
    monkeypatch.setattr(repo,"db_connection",connect)
    with pytest.raises(RuntimeError): repo.insert_snapshot(sample())
    connection.rollback.assert_called_once()
    connection.commit.assert_not_called()


def test_download_traversal_and_missing(monkeypatch,tmp_path):
    monkeypatch.setattr(export,"export_root",lambda:tmp_path)
    with pytest.raises(ValueError):
        export.download_path(dict(status="SUCCESS",file_path=str(tmp_path.parent/"secret.xlsx"),file_name="secret.xlsx"))
    with pytest.raises(FileNotFoundError):
        export.download_path(dict(status="SUCCESS",file_path=str(tmp_path/"missing.xlsx"),file_name="missing.xlsx"))


def test_internal_auth_before_repository(monkeypatch):
    app=FastAPI();app.include_router(api.router)
    lookup=MagicMock(); monkeypatch.setattr(repo,"list_files",lookup)
    client=TestClient(app)
    response=client.get("/api/v1/weekly-inventory/files")
    assert response.status_code in (401,403)
    lookup.assert_not_called()


def test_no_historical_snapshot():
    from backend.services.scheduler_service import run_scheduler_task
    with pytest.raises(ValueError, match="历史"):
        run_scheduler_task(sync.TASK_CODE,stat_month="2026-08")


def test_batch_does_not_delete_existing_rows(monkeypatch):
    connection=MagicMock();cursor=connection.cursor.return_value.__enter__.return_value
    @contextmanager
    def connect():yield connection
    monkeypatch.setattr(repo,"db_connection",connect)
    repo.insert_snapshot(sample())
    assert all(call.args[0].startswith("INSERT INTO") for call in cursor.executemany.call_args_list)
    cursor.execute.assert_not_called()
    connection.commit.assert_called_once()


def test_schema_matches_every_normalized_column():
    import re
    from pathlib import Path
    schema=(Path(__file__).parents[1]/'backend/schema.sql').read_text(encoding='utf-8')
    for group, table in repo.TABLES.items():
        definition=re.search(r'CREATE TABLE IF NOT EXISTS `'+table+r'` \((.*?)\) ENGINE',schema,re.S).group(1)
        columns=set(re.findall(r'^  `([^`]+)`',definition,re.M))
        assert set(sample()[group][0]) == columns-{'id','create_time','bin_identity_key'}
        assert 'snapshot_date`,`sync_batch_id`' in definition


@pytest.mark.parametrize('missing_product,registration_failure', [(False,False),(True,False),(False,True)])
def test_whole_chain_without_real_io(monkeypatch,tmp_path,missing_product,registration_failure):
    monkeypatch.setattr(repo,'require_bin_identity_schema',MagicMock())
    client=MagicMock()
    client.post_signed_query_auth.side_effect=[
        dict(code=0,total=1,data=[dict(wid=1,product_id=2,sku='SKU',product_total=3,purchase_price='1.25',extra={'keep':'raw'})]),
        dict(code=0,total=0,data=[]),
        dict(code=0,data=[] if missing_product else [dict(id=2,sku='SKU',product_name='产品')]),
    ]
    monkeypatch.setattr(sync,'LingXingClient',lambda **kwargs:client)
    monkeypatch.setattr(export,'export_root',lambda:tmp_path)
    begin=MagicMock();monkeypatch.setattr(repo,'begin_export',begin)
    stored={}
    def insert(groups):
        stored.update(groups)
        return sum(map(len,groups.values()))
    insert_mock=MagicMock(side_effect=insert)
    monkeypatch.setattr(repo,'insert_snapshot',insert_mock)
    monkeypatch.setattr(repo,'snapshot',lambda batch:stored)
    monkeypatch.setattr(repo,'warehouse_names',lambda:{1:'仓库'})
    finish=MagicMock(side_effect=[RuntimeError('registration failure'),None] if registration_failure else None)
    monkeypatch.setattr(repo,'finish_export',finish)
    if missing_product:
        with pytest.raises(ValueError,match='产品详情'):sync.sync_weekly_inventory()
        insert_mock.assert_not_called()
        assert not list(tmp_path.glob('*.xlsx'))
        assert finish.call_args.kwargs['error']
    elif registration_failure:
        with pytest.raises(RuntimeError,match='registration'):sync.sync_weekly_inventory()
        assert len(list(tmp_path.glob('*.xlsx'))) == 1  # preserve published evidence
        assert stored['inventory']
        assert finish.call_args.kwargs['error']
    else:
        result=sync.sync_weekly_inventory('manual')
        assert result['row_count']==1 and result['column_count']==25
        assert len(list(tmp_path.glob('*.xlsx')))==1
        assert stored['inventory'][0]['raw_json']['extra']=={'keep':'raw'}
        assert stored['inventory'][0]['sync_batch_id']==result['sync_batch_id']
        assert begin.call_args.args[-1]=='manual'


def test_scheduler_weekly_is_globally_locked_and_logged(monkeypatch):
    from backend.services import scheduler_service as scheduler
    connection=MagicMock(); logs=[];locks=[]
    @contextmanager
    def connect():yield connection
    @contextmanager
    def locked(name):
        locks.append(name)
        yield True
    monkeypatch.setattr(scheduler.repo,'performance_connection',connect)
    monkeypatch.setattr(scheduler.repo,'insert_scheduler_run',lambda conn,row:logs.append(row))
    monkeypatch.setattr(scheduler.repo,'named_lock',locked)
    runner=MagicMock(return_value=dict(sync_batch_id='b',extract_rows=1,ods_rows=1))
    monkeypatch.setattr(scheduler,'sync_weekly_inventory',runner)
    response=scheduler.run_scheduler_task(sync.TASK_CODE,trigger_type='JOB')
    assert response['status']=='completed'
    assert locks==['inventory:weekly-export']
    assert [row['status'] for row in logs]==['running','completed']
    runner.assert_called_once_with('JOB')
