package com.ruoyi.system.service.operation.customs;

import com.ruoyi.system.service.operation.external.lingxing.LingxingGatewayService;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import org.springframework.stereotype.Service;

/** STA送达时间只读查询；FBA单号先从领星STA列表解析，不同步或改写本地数据。 */
@Service
public class CustomsStaDeliveryDateService
{
    private static final String PLAN_API = "amzStaServer/openapi/inbound-plan/page";
    private static final String DATE_API = "amzStaServer/openapi/inbound-shipment/getDeliveryDateList";
    private static final ZoneId SHANGHAI = ZoneId.of("Asia/Shanghai");
    private static final long INTERVAL_NANOS = TimeUnit.MILLISECONDS.toNanos(1100);
    private final LingxingGatewayService gateway;
    private long nextRequestNanos;

    public CustomsStaDeliveryDateService(LingxingGatewayService gateway)
    {
        this.gateway = gateway;
    }

    public Map<String, Object> query(String inboundPlanId, String shipmentNo, Long sid) throws Exception
    {
        String plan = identifier(inboundPlanId, "STA任务编号");
        String shipment = identifier(shipmentNo, "货件单号");
        if (sid == null || sid <= 0) throw new IllegalArgumentException("SID必须为正整数");
        String shipmentId = shipment.regionMatches(true, 0, "FBA", 0, 3)
                ? resolveShipmentId(plan, shipment, sid) : shipment;
        Map<String, Object> request = Map.of("inboundPlanId", plan, "shipmentId", shipmentId, "sid", sid);
        Map<String, Object> response = postQuery(DATE_API, request);
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("inboundPlanId", plan);
        result.put("shipmentNo", shipment);
        result.put("shipmentId", shipmentId);
        result.put("sid", sid);
        result.put("queriedAt", OffsetDateTime.now(SHANGHAI).toString());
        result.put("response", response);
        boolean success = successful(response);
        List<?> options = List.of();
        if (success)
        {
            Map<?, ?> data = map(response.get("data"));
            String returnedPlan = text(data.get("inboundPlanId"));
            String returnedShipment = text(data.get("shipmentId"));
            if ((!returnedPlan.isEmpty() && !plan.equals(returnedPlan))
                    || (!returnedShipment.isEmpty() && !shipmentId.equals(returnedShipment)
                        && !shipment.equals(returnedShipment)))
                throw new IllegalStateException("领星返回的STA或货件与查询参数不一致，请核对后重试");
            if (!(data.get("shipmentList") instanceof List<?> values))
                throw new IllegalStateException("领星返回成功，但缺少可选送达时间列表shipmentList");
            options = values;
        }
        result.put("success", success);
        result.put("message", success ? (options.isEmpty() ? "暂无可选送达时间" : "查询成功") : failureMessage(response));
        result.put("options", options);
        result.put("optionCount", options.size());
        return result;
    }

    private String resolveShipmentId(String plan, String shipment, Long sid) throws Exception
    {
        LocalDate end = LocalDate.now(SHANGHAI);
        var candidates = new LinkedHashSet<String>();
        boolean exhausted = false;
        for (int page = 1; page <= 10; page++)
        {
            Map<String, Object> body = new LinkedHashMap<>();
            body.put("page", page);
            body.put("length", 200);
            body.put("dateBegin", end.minusYears(1).toString());
            body.put("dateEnd", end.toString());
            body.put("dateType", 1);
            body.put("shipmentIdList", List.of(shipment));
            Map<String, Object> response = postQuery(PLAN_API, body);
            if (!successful(response)) throw new IllegalStateException("查询货件STA归属失败：" + failureMessage(response));
            Map<?, ?> data = map(response.get("data"));
            if (!(data.get("records") instanceof List<?> records))
                throw new IllegalStateException("领星STA列表响应缺少records，请检查接口返回");
            for (Object value : records)
            {
                Map<?, ?> record = map(value);
                if (!plan.equals(text(record.get("inboundPlanId"))) || !sid.equals(longValue(record.get("sid")))) continue;
                if (!(record.get("shipmentList") instanceof List<?> shipments)) continue;
                for (Object entry : shipments)
                {
                    Map<?, ?> item = map(entry);
                    if (shipment.equalsIgnoreCase(text(item.get("shipmentConfirmationId")))
                            || shipment.equals(text(item.get("shipmentId"))))
                    {
                        String id = text(item.get("shipmentId"));
                        if (!id.isEmpty()) candidates.add(id);
                    }
                }
            }
            Long pages = longValue(data.get("pages"));
            if (records.isEmpty() || (pages != null ? page >= pages : records.size() < 200))
            {
                exhausted = true;
                break;
            }
        }
        if (!exhausted) throw new IllegalStateException("STA货件查询超过10页，请缩小范围或填写接口shipmentId");
        if (candidates.isEmpty()) throw new IllegalArgumentException(
                "近一年STA记录中未找到该STA编号、货件单号和SID的对应关系，请核对三项参数；也可直接填写接口shipmentId");
        if (candidates.size() != 1) throw new IllegalStateException("该货件匹配到多个shipmentId，请核对STA和SID后重试");
        return candidates.iterator().next();
    }

    private synchronized Map<String, Object> postQuery(String path, Map<String, Object> body) throws Exception
    {
        // 接口令牌桶容量为1；同一实例中的查询统一限速，不改动共用HTTP客户端。
        long wait = nextRequestNanos - System.nanoTime();
        if (nextRequestNanos != 0 && wait > 0) TimeUnit.NANOSECONDS.sleep(wait);
        nextRequestNanos = System.nanoTime() + INTERVAL_NANOS;
        Map<String, Object> response = gateway.post(path, body);
        if (response == null) throw new IllegalStateException("领星查询返回空响应，请稍后重试");
        return response;
    }

    private static String identifier(String value, String label)
    {
        String result = text(value);
        if (result.isEmpty()) throw new IllegalArgumentException(label + "不能为空");
        if (result.length() > 128 || result.chars().anyMatch(Character::isISOControl))
            throw new IllegalArgumentException(label + "格式不正确，长度不能超过128且不能包含换行");
        return result;
    }

    private static boolean successful(Map<String, Object> response)
    {
        return "0".equals(text(response.get("code")));
    }

    private static String failureMessage(Map<String, Object> response)
    {
        String message = text(response.get("message"));
        if (message.isEmpty()) message = text(response.get("msg"));
        if (message.isEmpty()) message = "领星接口返回失败";
        String requestId = text(response.get("requestId"));
        if (requestId.isEmpty()) requestId = text(response.get("request_id"));
        return "code=" + text(response.get("code")) + "：" + message
                + (requestId.isEmpty() ? "" : "；requestId=" + requestId);
    }

    private static Map<?, ?> map(Object value) { return value instanceof Map<?, ?> data ? data : Map.of(); }
    private static String text(Object value) { return value == null ? "" : String.valueOf(value).trim(); }
    private static Long longValue(Object value)
    {
        try { return new BigDecimal(text(value)).longValueExact(); }
        catch (RuntimeException ignored) { return null; }
    }
}
