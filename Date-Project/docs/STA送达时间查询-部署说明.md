# STA可选送达时间查询

## 本轮功能

STA页面右上角新增“批量修改提交时间”按钮，弹窗填写STA任务编号、货件单号和店铺SID。
支持最多20条货件，逐条查询；单条失败不会中断其他货件。
结果显示送达时间ID、开始时间、结束时间、过期时间和原始响应。
本轮按用户确认只实现查询和展示，不包含选择窗口或提交修改，不注册提交接口。

Java入口：`POST /operations/customs/shipment-fee/delivery-dates/query`。
请求示例：

```json
{"inboundPlanId":"wf09b90e18-4ee8-4f05-ac03-1926aefe9292","shipmentNo":"FBA15MPTRK38","sid":12616}
```

入口沿用`customs:shipmentFee:list`查看权限，前后端均校验，不新增SQL或业务表。
使用既有领星网关鉴权，不向前端发送令牌或密钥。

FBA货件单号先通过`amzStaServer/openapi/inbound-plan/page`查询近一年STA关联，
同时核对STA任务编号、SID和货件单号，再向
`amzStaServer/openapi/inbound-shipment/getDeliveryDateList`传入返回的shipmentId。
直接填写接口shipmentId时跳过关联查询。全程不调用STA同步入库或任何修改接口。
接口调用在同一服务实例内串行限速，间隔至少1.1秒。
原始返回的送达时间列表不自行补日期、不过滤旧窗口、不推测可提交状态。

## 实际只读验证

2026-10-26北京时间09:35～09:37，使用项目现有配置实际查询：

- 将`FBA15MPTRK38`直接作为shipmentId，接口返回code=-1：查询不到对应的货件shipment数据。
- STA列表接口返回code=0，确认指定inboundPlanId、SID=12616与货件单号对应。
- 返回的shipmentId为`sh1e6056c7-9aab-4a43-b409-7f8145e73643`；
  shipmentConfirmationId为`FBA15MPTRK38`。
- 使用该shipmentId查询可选送达时间，返回code=0、11个选项，
  requestId=`08c9714017fb41eda8e7031806675b55.1792978628364`。
- 示例：2026-10-25至2026-10-31，deliveryWindowOptionId=
  `dw222e6e44-a700-4bf3-bdae-0a265dda4868`；validUntil=2027-01-02。

以上为查询时的接口结果，实际可选时间应以点击查询后的最新返回为准。
没有提交修改送达时间，也没有更新本地STA业务表。

## 部署及后续

重新打包并重启Java，构建部署前端。无需执行SQL，无需重启Python。
页面输入变化会清除对应旧结果；关闭弹窗后停止后续请求并忽略尚在执行的旧查询响应。
本次只提供查询阶段；后续提交必须以重新查询得到的送达时间ID为准。
提供的文档参数表写startDate/endDate，提交示例却写startTime/endTime，
接入提交前须核实这处文档差异，本次未尝试任何提交参数。
