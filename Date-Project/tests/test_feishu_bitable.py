"""飞书多维表格客户端：全部用假传输层，不发真实请求、不需要凭证。"""
import json
from decimal import Decimal
from types import SimpleNamespace

import httpx
import pytest

from backend.integrations.feishu.client import (
    FeishuClient,
    FeishuRequestError,
    field_text,
    parse_bitable_url,
)

REAL_URL = "https://scnmv3if5x1t.feishu.cn/base/UjvXbOPJTalrRKsmZKpcUjQ5nEe?table=tbl4cDY58uZmiYU1&view=vew4MoiWFe"


def config(**kw):
    base = dict(feishu_endpoint="https://open.feishu.cn", feishu_app_id="cli_x", feishu_app_secret="sec_x",
                feishu_token_refresh_before_sec=300, feishu_request_timeout_sec=5,
                feishu_min_request_interval_sec=0, feishu_max_retries=2, feishu_page_size=500)
    return SimpleNamespace(**{**base, **kw})


def ok(payload):
    return httpx.Response(200, json=payload)


def client(handler, **kw):
    calls = []

    def capture(request):
        calls.append(request)
        return handler(request, len(calls) - 1)

    instance = FeishuClient(config(**kw), transport=httpx.MockTransport(capture))
    return instance, calls


def token_then(pages):
    """第一次调用返回令牌，之后按顺序返回给定的业务响应。"""
    def handler(request, index):
        if index == 0:
            return ok({"code": 0, "msg": "ok", "tenant_access_token": "t-abc", "expire": 7200})
        return ok(pages[index - 1])
    return handler


# ---------------------------------------------------------------- 地址解析

def test_parse_real_bitable_url():
    assert parse_bitable_url(REAL_URL) == ("UjvXbOPJTalrRKsmZKpcUjQ5nEe", "tbl4cDY58uZmiYU1", "vew4MoiWFe")


def test_url_without_view_is_allowed():
    app, table, view = parse_bitable_url("https://x.feishu.cn/base/App1?table=tbl1")
    assert (app, table, view) == ("App1", "tbl1", "")


@pytest.mark.parametrize("url", [
    "https://x.feishu.cn/wiki/Node1?table=tbl1",   # 知识库地址给的是node_token，不是app_token
    "https://x.feishu.cn/base/App1",               # 缺 table
    "https://x.feishu.cn/sheets/Sh1?table=tbl1",   # 不是多维表格
    "", None,
])
def test_bad_urls_rejected_with_reason(url):
    with pytest.raises(FeishuRequestError):
        parse_bitable_url(url)


# ------------------------------------------------------------------ 凭证

@pytest.mark.parametrize("missing", ["feishu_app_id", "feishu_app_secret"])
def test_missing_credentials_refused_before_any_request(missing):
    with pytest.raises(FeishuRequestError, match="FEISHU_APP_ID"):
        FeishuClient(config(**{missing: ""}))


def test_endpoint_must_be_clean_https():
    for bad in ("http://open.feishu.cn", "https://u:p@open.feishu.cn", "https://open.feishu.cn?a=1"):
        with pytest.raises(FeishuRequestError, match="HTTPS"):
            FeishuClient(config(feishu_endpoint=bad))


def test_secret_only_in_token_body_never_in_headers_or_urls():
    """凭证只出现在换令牌的请求体里；其余请求一律只带 Bearer。"""
    instance, calls = client(token_then([{"code": 0, "data": {"items": [], "has_more": False}}]))
    with instance:
        list(instance.iter_records("App1", "tbl1", "vew1"))
    token_request, records_request = calls[0], calls[1]
    assert json.loads(token_request.content) == {"app_id": "cli_x", "app_secret": "sec_x"}
    assert "Authorization" not in token_request.headers
    assert records_request.headers["Authorization"] == "Bearer t-abc"
    assert all("sec_x" not in str(c.url) for c in calls)
    assert "sec_x" not in str(records_request.headers)


def test_token_reused_across_calls_not_refetched_each_page():
    pages = [{"code": 0, "data": {"items": [{"record_id": "r1", "fields": {}}], "has_more": True, "page_token": "p2"}},
             {"code": 0, "data": {"items": [{"record_id": "r2", "fields": {}}], "has_more": False}}]
    instance, calls = client(token_then(pages))
    with instance:
        assert [r["record_id"] for r in instance.iter_records("App1", "tbl1")] == ["r1", "r2"]
    # 1次换令牌 + 2页，没有反复换令牌。
    assert len(calls) == 3


def test_expired_token_refreshed_once_then_request_retried():
    """令牌可能在翻页途中过期；换一次再重试，不能直接失败。"""
    def handler(request, index):
        if index in (0, 2):
            return ok({"code": 0, "tenant_access_token": f"t-{index}", "expire": 7200})
        if index == 1:
            return ok({"code": 99991663, "msg": "token expired"})
        return ok({"code": 0, "data": {"items": [{"record_id": "r1", "fields": {}}], "has_more": False}})

    instance, calls = client(handler)
    with instance:
        assert [r["record_id"] for r in instance.iter_records("App1", "tbl1")] == ["r1"]
    assert calls[3].headers["Authorization"] == "Bearer t-2"


# ------------------------------------------------------------------ 翻页

def test_pagination_passes_page_token_and_view_id():
    pages = [{"code": 0, "data": {"items": [{"record_id": "r1", "fields": {}}], "has_more": True, "page_token": "p2"}},
             {"code": 0, "data": {"items": [{"record_id": "r2", "fields": {}}], "has_more": False, "page_token": ""}}]
    instance, calls = client(token_then(pages))
    with instance:
        list(instance.iter_records("App1", "tbl1", "vew1"))
    assert "page_token" not in str(calls[1].url)
    assert "page_token=p2" in str(calls[2].url)
    assert json.loads(calls[1].content)["view_id"] == "vew1"
    assert "App1" in str(calls[1].url) and "tbl1" in str(calls[1].url)


def test_has_more_true_but_no_page_token_stops_instead_of_looping():
    """游标没推进就停下，不然会把同一页无限拉下去。"""
    pages = [{"code": 0, "data": {"items": [{"record_id": "r1", "fields": {}}], "has_more": True, "page_token": ""}}]
    instance, calls = client(token_then(pages))
    with instance:
        assert len(list(instance.iter_records("App1", "tbl1"))) == 1
    assert len(calls) == 2


def test_view_id_omitted_when_not_given():
    instance, calls = client(token_then([{"code": 0, "data": {"items": [], "has_more": False}}]))
    with instance:
        list(instance.iter_records("App1", "tbl1"))
    assert "view_id" not in json.loads(calls[1].content)


def test_fetch_records_limit_stops_early():
    pages = [{"code": 0, "data": {"items": [{"record_id": f"r{i}", "fields": {}} for i in range(5)],
                                  "has_more": True, "page_token": "p2"}}]
    instance, calls = client(token_then(pages))
    with instance:
        assert len(instance.fetch_records("App1", "tbl1", limit=2)) == 2
    # 限量取到就停，不再翻下一页。
    assert len(calls) == 2


# ------------------------------------------------------------------ 错误

def test_business_code_surfaces_feishu_message():
    """飞书把错误放在 HTTP 200 的响应体里，必须查 code，不能只看状态码。"""
    instance, _ = client(token_then([{"code": 91403, "msg": "Forbidden"}]))
    with instance, pytest.raises(FeishuRequestError, match="91403"):
        list(instance.iter_records("App1", "tbl1"))


def test_permission_error_not_retried():
    instance, calls = client(token_then([{"code": 91403, "msg": "Forbidden"}] * 5))
    with instance, pytest.raises(FeishuRequestError):
        list(instance.iter_records("App1", "tbl1"))
    assert len(calls) == 2  # 换令牌 + 1次请求，没有重试


def test_rate_limit_retried_then_succeeds():
    pages = [{"code": 99991400, "msg": "too many request"},
             {"code": 0, "data": {"items": [{"record_id": "r1", "fields": {}}], "has_more": False}}]
    instance, calls = client(token_then(pages))
    with instance:
        assert len(list(instance.iter_records("App1", "tbl1"))) == 1
    assert len(calls) == 3


def test_missing_token_in_response_is_an_error():
    instance, _ = client(lambda r, i: ok({"code": 0, "msg": "ok"}))
    with instance, pytest.raises(FeishuRequestError, match="tenant_access_token"):
        instance.token()


# ------------------------------------------------------------------ 取数

def test_numbers_decoded_as_decimal_not_float():
    """多维表格里的金额/数量不能经过float，否则会被改写。"""
    pages = [{"code": 0, "data": {"items": [{"record_id": "r1", "fields": {"佣金比例": 0.1}}],
                                  "has_more": False}}]
    instance, _ = client(token_then(pages))
    with instance:
        value = next(iter(instance.iter_records("App1", "tbl1")))["fields"]["佣金比例"]
    assert isinstance(value, Decimal) and str(value) == "0.1"


def test_list_fields_paginates_and_returns_definitions():
    pages = [{"code": 0, "data": {"items": [{"field_name": "卖家", "type": 1, "is_primary": True}],
                                  "has_more": True, "page_token": "p2"}},
             {"code": 0, "data": {"items": [{"field_name": "级别", "type": 3}], "has_more": False}}]
    instance, calls = client(token_then(pages))
    with instance:
        fields = instance.list_fields("App1", "tbl1")
    assert [f["field_name"] for f in fields] == ["卖家", "级别"]
    assert calls[1].method == "GET" and "/fields" in str(calls[1].url)


# -------------------------------------------------------------- 字段展示

@pytest.mark.parametrize("value,expected", [
    ("金牌", "金牌"),
    (Decimal("0.1"), "0.1"),
    (True, "是"),
    (False, "否"),
    (None, ""),
    ([{"type": "text", "text": "多行"}, {"type": "text", "text": "文本"}], "多行, 文本"),
    ([{"name": "张三"}, {"name": "李四"}], "张三, 李四"),
    ({"link": "https://x"}, "https://x"),
])
def test_field_text_flattens_common_shapes(value, expected):
    assert field_text(value) == expected
