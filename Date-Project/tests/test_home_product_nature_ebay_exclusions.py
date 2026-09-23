from backend.services import home_product_nature_service as s
from test_home_product_nature import NOW, row, source, EBAY


def test_ebay_amz_prefix_excluded_but_other_unassigned_retained():
    rows=[row(' amz-CFX-1 '),row('AMZOTHER'),row('B0GKFJCC2B'),row('ABC-AMZ-1')]
    report,facts=s.build('ebay',source(rows,EBAY),NOW)
    assert {f['sku'] for f in facts}=={'B0GKFJCC2B','ABC-AMZ-1'}
    assert report['audit']['excluded_amz_rows']==2
    assert report['reconciliation']['legacy_total']==4
    assert report['reconciliation']['comparable_total']==2
    assert report['reconciliation']['excluded_amz_sku_count']==2
    assert any(f['principal_name']=='未分配' for f in facts)
    assert report['segments'][0]['sku_count']==2


def test_duplicate_amz_listings_audit_rows_separate_from_unique_skus():
    rows=[row('AMZ-1'),{**row('AMZ-1'),'store_id':'2'},row('CL-1')]
    report,_=s.build('ebay',source(rows,EBAY),NOW)
    assert report['audit']['excluded_amz_rows']==2
    assert report['reconciliation']['excluded_amz_sku_count']==1
    assert report['sku_count']==1 and report['reconciliation']['cl_skus']


def test_exclusion_does_not_touch_amz_platform():
    report,facts=s.build('amz',source([row('AMZ-1')]),NOW)
    assert report['sku_count']==1 and facts[0]['sku']=='AMZ-1'
    assert report['audit'].get('excluded_amz_rows',0)==0


def test_all_amz_ebay_population_yields_empty_not_error():
    report,facts=s.build('ebay',source([row('AMZ-1')],EBAY),NOW)
    assert report['state']=='EMPTY' and report['sku_count']==0 and facts==[]
