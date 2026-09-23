import pytest
from backend.services import home_product_nature_service as s
from test_home_product_nature import NOW, row, source, EBAY


@pytest.mark.parametrize('region,age,expected',[
    ('US',60,'NEW'),('US',61,'OLD'),('US',None,'OLD'),
    ('EU',90,'NEW'),('EU',91,'OLD'),('EU',None,'OLD')])
def test_amz_valid_date_within_limit_else_old(region,age,expected):
    item={**row(age=age),'replenishment_regions':[region]}
    report,facts=s.build('amz',source([item]),NOW)
    assert facts[0]['nature']==expected
    assert report['counts'][expected]==1
    assert report['counts']['UNKNOWN']==0


def test_missing_date_no_region_still_unknown_and_ebay_unchanged():
    report,_=s.build('amz',source([{**row(age=None),'replenishment_regions':[]}]),NOW)
    assert report['counts']['UNKNOWN']==1
    report,_=s.build('ebay',source([row(age=None)],EBAY),NOW)
    assert report['counts']['UNKNOWN']==1


def test_mixed_missing_date_and_new_listing_uses_valid_date():
    report,_=s.build('amz',source([row(age=None),{**row(age=10),'store_id':'2'}]),NOW)
    assert report['counts']==dict(NEW=1,OLD=0,UNKNOWN=0,CONFLICT=0)
