from unittest.mock import MagicMock
import pytest
from backend.services import home_product_nature_service as s
from backend.repositories import home_product_nature_repository as r
from test_home_product_nature import NOW, fake_transaction, source


@pytest.mark.parametrize('start,end',[('2025-09','2026-09'),('2026-09','2026-08'),('2026-09','2026-10'),('2026-9','2026-09')])
def test_bad_range_rejected_before_db(monkeypatch,start,end):
    monkeypatch.setattr(s,'now',lambda:NOW)
    tx=MagicMock();monkeypatch.setattr(r,'transaction',tx)
    with pytest.raises(ValueError):s.get_history('amz',start,end)
    tx.assert_not_called()


def test_past_custom_range_is_readonly_and_fills_gaps(monkeypatch):
    monkeypatch.setattr(s,'now',lambda:NOW)
    conn,_=fake_transaction(monkeypatch)
    history=MagicMock(return_value=[]);monkeypatch.setattr(r,'history',history)
    load=MagicMock();monkeypatch.setattr(s,'_load',load)
    result=s.get_history('amz','2024-10','2025-09',True)
    assert len(result['items'])==12
    assert result['items'][0]['stat_month']=='2024-10'
    assert all(i['sku_count'] is None for i in result['items'])
    load.assert_not_called();conn.commit.assert_not_called()
    assert history.call_args.args[2:]==('2025-09','2024-10')


@pytest.mark.parametrize('platform',['amz','ebay'])
def test_current_live_point_explicit_not_frozen(monkeypatch,platform):
    monkeypatch.setattr(s,'now',lambda:NOW)
    conn,_=fake_transaction(monkeypatch)
    monkeypatch.setattr(r,'history',lambda *a:[])
    report,_=s.build('amz',source(),NOW)
    load=MagicMock(return_value=report);monkeypatch.setattr(s,'_load',load)
    result=s.get_history(platform,'2026-09','2026-09',True)
    assert len(result['items'])==1 and result['items'][0]['provisional'] is True
    load.assert_called_once();conn.commit.assert_called_once()


def test_missing_current_source_has_message_not_zero(monkeypatch):
    monkeypatch.setattr(s,'now',lambda:NOW);fake_transaction(monkeypatch)
    monkeypatch.setattr(r,'history',lambda *a:[])
    monkeypatch.setattr(s,'_load',lambda *a:dict(stat_month='2026-09',state='MISSING_RULES',sku_count=None,message='缺负责人规则'))
    item=s.get_history('amz','2026-09','2026-09',True)['items'][0]
    assert item['sku_count'] is None and item['message']=='缺负责人规则'
