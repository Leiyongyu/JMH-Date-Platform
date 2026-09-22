# Excel店铺凭证读取及到期提醒（2026-09-19）

## 本次变化

月度任务不再固定只读一个DPAPI账号。只要配置了EBAY_SELLER_ACCOUNTS_FILE，优先读取指定Excel；原EBAY_SELLER_ACCOUNTS配置作为未设置文件时的旧方式，不与Excel混合拉取。

现有文件有96行店铺，其中41行为eBay，37行填写秘钥，4行空白。只读取eBay行；空秘钥直接跳过、不告警、不删除该店旧数据。其他平台的行不参与调用。

工作表为“紫鸟店铺”，必需列：店铺名称、平台、店铺账号、browserId，最后一列必须为“秘钥”。拒绝公式/错误型凭证单元格、重复browserId、重复密钥及非文本密钥。每次执行重新读取文件，无须把明文密钥复制进.env、数据库或代码。

应用凭证EBAY_CLIENT_ID / EBAY_CLIENT_SECRET继续读取现有.env。Excel中的“店铺账号”可能是登录邮箱，不当作eBay卖家用户名；每店先通过官方Identity确认username及稳定userId，再读商品。原始表seller_account保存真实卖家名，response_meta_json.source_shop保存Excel店铺名称、browserId及源行号用于追溯，不保存密钥。

保持上一轮完整发布策略：所有有凭证账号均完成身份及分页校验后才统一事务写入；任何一个失败，本批不覆盖旧数据。不会因403而跳过身份校验。不同配置行解析到同一userId时拒绝重复发布。

## .env配置

```dotenv
EBAY_SELLER_ACCOUNTS_FILE=data/紫鸟店铺全量.xlsx
EBAY_SELLER_ACCOUNTS_SHEET=紫鸟店铺
EBAY_SELLER_TOKEN_EXPIRES_ON=2028-03-18
```

相对路径相对于Date-Project目录，不取进程当前目录。部署机把Excel安全复制到自己的Date-Project/data目录，限制文件读取权限；Excel本身包含明文授权密钥，并非加密保管箱。.env和本文件名已加入Git忽略，不要强制git add。无需复制本机DPAPI文件。

## 有效期及提醒

用户确认本批预计2028-03-18前后到期，因此统一默认按2028-03-18计算，提醒起始2028-02-18；不是通过解析Token推断的到期日。

以后各店日期不同，可在最后的“秘钥”列前增加“授权日期”或“到期日期”。优先级：本行到期日期 > 本行授权日期加18个自然月 > .env统一到期日期。日期格式YYYY-MM-DD或Excel日期；没有日期会标为UNKNOWN_EXPIRY，绝不从导入日、文件修改时间或“IP已过期”推测。

Java每天北京时间09:00执行独立检查（Spring @Scheduled，Asia/Shanghai），不依赖每月5日05:00的商品同步任务，不访问eBay、不拉商品。提醒窗口为到期前一个自然月起；进入窗口或已过期时每日汇总提醒一次。同日期状态相同的店铺合并一条，最多展示8个名称，其余显示数量；Redis去重，发送失败不记成功。

发送渠道是现有sync.alert.webhook-url / SYNC_ALERT_WEBHOOK_URL对应的企微机器人群消息，**不是电子邮件**，没有擅自配置SMTP或收件邮箱。提醒开关：ebay.credentials.reminder.enabled（默认true）。原有sync.alert.enabled也必须启用，Webhook和Redis须可用。

只读元数据接口：GET /api/v1/internal/scheduler/ebay-credentials/expiry，需要X-Internal-Token。仅返回店铺标识、状态、到期/提醒日期，不返回密钥或应用Secret。

密钥实际可能提前撤销，定时同步失败仍走原失败告警；有效期提醒不能代替实时授权验证。每次换密钥后应同步更新相应到期日期，不能只替换密钥值。

## 部署及验证

本节仅指Excel接入与每日到期提醒，无需单独SQL。后续新增的月末真实健康检查需要03/04脚本，见 [月末健康检查部署说明.md](月末健康检查部署说明.md)。上一轮两张商品原始表及月度Quartz任务SQL仍须已部署。

1. 更新Java/Python代码；安全复制Excel，填好以上.env配置。
2. 重启Python以加载.env；重启Java以加载每日检查服务。无需新增Quartz行，月度商品任务仍为每月5日05:00。
3. 查看脱敏到期接口，预期37个账号VALID、remind_on=2028-02-18；4个缺密钥行只作统计，不发提醒。
4. 身份及商品权限确认无误后，再手动执行月度商品同步。

## 2026-09-19 只读实测与限制

- 已逐店尝试37个身份查询：15个成功、19个HTTP 403、3个网络失败，不能宣称37个全部可拉取。
- 针对第22行补充诊断：OAuth HTTP200，Identity HTTP403，错误ID1100。eBay官方将1100定义为权限不足：https://edp.ebay.com/develop/api/sell/error_codes 。这不是密钥到期证据；需要检查相应店铺授权给当前应用的权限。不能仅凭本次结果认定其他失败店同一原因。
- 网络失败行：25、30、59；可重试验证。其他403行：22、26、31、35、36、38、39、41、42、44、46、47、48、49、51、53、55、57、60。
- 本轮未执行完整商品同步或写入商品表，未发送真实测试提醒，未重启服务。
- 后续复核：25、30、59行网络失败均重试成功，因此最终为18个身份成功、19个403未解决。第21行allteile-motor通过Excel凭证读取了5条真实商品，Ack=Success，接口报告总数202；未全量下载或写库。
- 回归：Python相关129项通过，Java提醒与新旧任务共7项通过。均未使用真实Webhook发送测试消息。

### 同日补充：Trading健康检查已验证

37家全部通过OAuth、Trading GetUser身份核对、GetMyeBaySelling第一页查询，在售总数合计18,059。4家缺密钥按要求跳过。健康报告已存入新增的ebay_token_health_run表；健康检查本身未全量拉商品，未发送企微测试消息。前述19家REST Identity HTTP403是另一条接口路径的问题，不代表密钥失效。后续商品同步修复及全量验证以[商品同步403修复说明.md](商品同步403修复说明.md)为准。
