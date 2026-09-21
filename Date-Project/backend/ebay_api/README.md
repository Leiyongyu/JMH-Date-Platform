# eBay 卖家接口模块

独立于价格查询 `backend/ebay_tool` 和领星刊登同步。提供店铺身份核对、Trading API在售分页查询及标准化解析；同步服务已接入独立Python原始表和受内部令牌保护的定时任务，没有公开HTTP路由或修改eBay店铺的接口。

## 凭证

月度同步优先读取.env中EBAY_SELLER_ACCOUNTS_FILE指定的Excel，最后一列为秘钥，空密钥跳过。详见[商品采集部署说明](../../deploy/ebay-store-listing/部署说明_商品采集.md)。本次发布包含凭证读取及有效期元数据查询，不包含独立健康检查或主动到期提醒任务。下面的DPAPI方式仍可用于单店CLI及未配置Excel时的旧模式。

本项目 `.env` 已有 `EBAY_CLIENT_ID` / `EBAY_CLIENT_SECRET`（不提交Git）。卖家接口还必须有对应店铺的Refresh Token，不能用价格搜索的App Token替代。

以下两种方式选一：

- 设置 `EBAY_REFRESH_TOKEN`，由服务环境或本机未跟踪的 `.env` 提供。
- Windows设置 `EBAY_REFRESH_TOKEN_DPAPI_FILE`，指向现有 `ConvertFrom-SecureString` 加密文件。必须在创建文件的电脑和Windows账户下运行；部署机不能直接复制文件保证可用。CLI的 `--token-file` 优先于环境配置。

本模块不扫描或复制其他项目凭证，不记录Token、HTTP请求头或错误响应正文；应用实例缓存Access Token，过期前120秒重新获取。TLS证书校验开启，拒绝HTTP重定向。连接中断、超时及明确的临时TLS断连共享最多3次请求预算（等待5秒、15秒），只重试原请求，不推进页码；证书校验失败、主机名不匹配、未知SSL错误、HTTP错误及业务校验失败不重试。TLS诊断仅记录受限异常类型及结构化原因码，不输出异常正文、URL或凭证。

## 小样本命令

在 Date-Project 目录运行（不会写文件或数据库）：

```powershell
$tokenFile = Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'JMH-Secrets/ebay-test-refresh-token.dpapi'
.\.venv\Scripts\python.exe -m backend.ebay_api --expected-seller ace-autoteile --page-size 5 --token-file $tokenFile
```

预期店铺账号是必填校验值；先调身份接口，账号不符就停止，不继续拿Listing。命令只拿第一页，控制台最多显示5条，不输出原始XML或密钥。

Python复用：

```python
from backend.ebay_api import EbayCredentials, EbaySellerClient

client = EbaySellerClient(EbayCredentials.from_env())
try:
    result = client.active_listings_page(
        page=1, page_size=100, expected_username='ace-autoteile')
    # result['items']：标准字段；result['raw_xml']：完整原始响应。
finally:
    client.close()
```

全量同步由 `backend/services/ebay_store_listing_sync_service.py` 实现跨页重复检测、总数/分页完整性核验及多账号原子发布；CLI仍只查询单页。部署与多账号凭证配置见 [商品采集部署说明](../../deploy/ebay-store-listing/部署说明_商品采集.md)。

定时任务：`ebay_store_listing_sync`，每月5日北京时间05:00。原始表 `ods_ebay_store_listing_latest` 按稳定账号ID隔离覆盖，`seller_account` 保存店铺用户名。`ods_ebay_store_listing_state` 保存每账号最新成功状态。完整商品XML保留在raw_xml；完整响应信封（移除ItemArray）保留在response_meta_json，不保存请求令牌。

## 接口与口径

1. OAuth：POST `https://api.ebay.com/identity/v1/oauth2/token`，grant_type=refresh_token。
2. Excel同步和默认单页查询的身份：Trading `GetUser`，核对预期用户名/邮箱；不再依赖REST Identity权限。稳定账号键为 `trading:` + SHA-256(EIASToken)，EIASToken是不可变用户标识而非OAuth密钥；不保存GetUser原始XML、邮箱或EIASToken原值。身份在客户端内按Access Token缓存，Token更新后重新核验。旧JSON账号配置仍保留REST Identity及原user_id，不隐式改写旧配置。
3. 在售：POST `https://api.ebay.com/ws/api.dll`，`GetMyeBaySelling`，Token使用 `X-EBAY-API-IAF-TOKEN`；兼容版本1193、SITEID=0。

- 只请求ActiveList，显式关闭Scheduled/Sold/Unsold；HideVariations=false，保留变体SKU和原始XML。
- 检查HTTP状态和XML Ack；Failure/PartialFailure不当成功或空数据，错误仅输出数字错误码。Warning返回警告码。
- 请求ActiveList但响应缺少该节点时，记录Ack、受限数字警告码、页码、响应字节数。仅Ack=Success且无Error业务错误时重试相同页，与网络/TLS共用最多3次请求预算；Warning缺节点直接失败。持续缺节点不作为空库存，不跳页、不发布部分数据。
- 本模块分页保守上限100，小样本支持1–100。参考项目的“必须100”不是小样本限制：[官方参考示例](https://developer.ebay.com/devzone/xml/docs/reference/ebay/GetMyeBaySelling.html)使用每页3条，每页5条已实测通过。2026-09-19已按每页100条完成37家/18,059条全量同步与入库核对，详见[403修复记录](../../deploy/ebay-store-listing/商品同步403修复说明.md)。未对每页200条作验证。
- `item_id`是刊登标识，同一SKU可能有多个刊登；页内ItemID重复报错，不静默丢行。
- `current_price.value`通过Decimal校验，以字符串返回；`currency`取原始currencyID，不换汇。
- `quantity`是刊登总量；`quantity_available`是当前可售数量；`quantity_sold`是接口已售数量。零值保留，缺失为None，不自行用相减补值。
- `site`从商品URL的真实hostname匹配，不用币种推断，也不把账号注册站点当作商品站点。
- 顶层SKU为空的多变体商品仍保留，子SKU在variations；未实现按变体展开的业务统计。
- 原始响应最大10MB，只接收UTF-8 XML，禁止DTD和实体定义。

## 2026-09-18 只读实测

返回时间 `2026-09-18T08:31:33.317Z`（北京时间16:31:33）。授权账号 `ace-autoteile`，账号注册站点EBAY_HK；不能据此认为商品都在香港站。

请求page=1、page_size=5；Ack=Success；返回5条，接口报告总数471、总页数95、has_more=true。只调用一次OAuth、一次身份接口、一次Trading查询，没有全量拉取。

| SKU | 商品站点 | 现价 | 可售数量 | 已售数量 |
| --- | --- | --- | ---: | ---: |
| DAS-10290-0040 | UK | 14.41 GBP | 16 | 28 |
| MCD-20011-0022 | FR | 39.99 EUR | 4 | 47 |
| MCD-20021-0051 | UK | 24.59 GBP | 36 | 3 |
| BMW-30226-0242 | UK | 12.22 GBP | 0 | 46 |
| FRD-70330-0738 | UK | 17.5 GBP | 28 | 缺失 |

数据会随店铺变动，本表仅为本次验收记录。0库存仍可在ActiveList中，不等于接口出错。471是接口报告值，本次未全量下载核对。

测试：`.venv/Scripts/python.exe -m pytest tests/test_ebay_api.py -q`。
