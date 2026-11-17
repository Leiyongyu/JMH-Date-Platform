package com.ruoyi.system.service.operation.external.lingxing;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.system.domain.operation.external.LingxingStaInboundPlan;
import com.ruoyi.system.domain.operation.external.LingxingStaInboundPlanItem;
import com.ruoyi.system.domain.operation.external.LingxingStaInboundPlanShipment;
import com.ruoyi.system.mapper.operation.external.LingxingStaInboundPlanMapper;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.util.StringUtils;

/** 领星STA任务同步：空表初始化最近一年，已有数据增量同步最近三天。 */
@Service
public class LingxingStaInboundPlanSyncService
{
    private static final Logger LOG =
            LoggerFactory.getLogger(LingxingStaInboundPlanSyncService.class);
    private static final String API_PATH = "amzStaServer/openapi/inbound-plan/page";
    private static final int PAGE_SIZE = 200;
    private static final int MAX_PAGES = 100;
    private static final long RATE_LIMIT_DELAY_MS = 1100L;
    private static final DateTimeFormatter DATE = DateTimeFormatter.ISO_LOCAL_DATE;
    private static final List<DateTimeFormatter> DATE_TIMES = List.of(
            DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss"),
            DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm"),
            DateTimeFormatter.ISO_LOCAL_DATE_TIME);

    private final LingxingGatewayService gateway;
    private final LingxingStaInboundPlanMapper mapper;
    private final ObjectMapper objectMapper;
    private final TransactionTemplate transactionTemplate;

    public LingxingStaInboundPlanSyncService(
            LingxingGatewayService gateway,
            LingxingStaInboundPlanMapper mapper,
            ObjectMapper objectMapper,
            TransactionTemplate transactionTemplate)
    {
        this.gateway = gateway;
        this.mapper = mapper;
        this.objectMapper = objectMapper;
        this.transactionTemplate = transactionTemplate;
    }

    public Map<String, Object> syncByShipmentId(String shipmentId) throws Exception
    {
        String normalizedShipmentId = trim(shipmentId);
        if (!StringUtils.hasText(normalizedShipmentId))
            throw new IllegalArgumentException("货件ID或货件单号不能为空");
        if (normalizedShipmentId.length() > 128)
            throw new IllegalArgumentException("货件ID或货件单号长度不能超过128");

        LocalDate dateEnd = LocalDate.now();
        return syncRange(
                dateEnd.minusYears(1), dateEnd, normalizedShipmentId, "MANUAL_SHIPMENT");
    }

    public Map<String, Object> syncAuto() throws Exception
    {
        LocalDate dateEnd = LocalDate.now();
        boolean initialSync = mapper.countAllPlans() == 0;
        LocalDate dateBegin = initialSync
                ? dateEnd.minusYears(1) : dateEnd.minusDays(2);
        return syncRange(dateBegin, dateEnd, null,
                initialSync ? "INITIAL_ONE_YEAR" : "INCREMENTAL_THREE_DAYS");
    }

    private Map<String, Object> syncRange(
            LocalDate dateBegin, LocalDate dateEnd,
            String shipmentId, String syncMode) throws Exception
    {
        long startedAt = System.currentTimeMillis();
        LinkedHashMap<String, PlanBundle> bundles = new LinkedHashMap<>();
        long remoteTotal = 0L;
        int fetchedPages = 0;

        for (int page = 1; page <= MAX_PAGES; page++)
        {
            Map<String, Object> body = new LinkedHashMap<>();
            body.put("page", page);
            body.put("length", PAGE_SIZE);
            body.put("dateBegin", dateBegin.format(DATE));
            body.put("dateEnd", dateEnd.format(DATE));
            body.put("dateType", 1);
            if (StringUtils.hasText(shipmentId))
                body.put("shipmentIdList", List.of(shipmentId));

            Map<String, Object> response = gateway.post(API_PATH, body);
            validateResponse(response);
            Map<String, Object> data = mapValue(response.get("data"));
            List<Map<String, Object>> records = listValue(data.get("records"));
            Long total = longValue(data.get("total"));
            if (total != null) remoteTotal = total;
            fetchedPages++;

            for (Map<String, Object> record : records)
            {
                PlanBundle bundle = toBundle(record, shipmentId);
                bundles.put(bundle.plan.getRecordKey(), bundle);
            }

            LOG.info("领星STA任务同步 mode={}, shipmentId={}, page={}, records={}, total={}",
                    syncMode, shipmentId, page, records.size(), remoteTotal);
            Long pages = longValue(data.get("pages"));
            if (records.isEmpty()
                    || (pages != null && page >= pages)
                    || (remoteTotal > 0 && bundles.size() >= remoteTotal))
                break;
            Thread.sleep(RATE_LIMIT_DELAY_MS);
        }

        List<String> inboundPlanIds = bundles.values().stream()
                .map(bundle -> bundle.plan.getInboundPlanId())
                .filter(StringUtils::hasText)
                .distinct()
                .toList();
        int[] itemCount = {0};
        int[] shipmentCount = {0};
        transactionTemplate.executeWithoutResult(status -> {
            for (PlanBundle bundle : bundles.values())
            {
                mapper.upsertPlan(bundle.plan);
                mapper.deleteItemsByRecordKey(bundle.plan.getRecordKey());
                mapper.deleteShipmentsByRecordKey(bundle.plan.getRecordKey());
                if (!bundle.items.isEmpty())
                {
                    mapper.batchInsertItems(bundle.items);
                    itemCount[0] += bundle.items.size();
                }
                if (!bundle.shipments.isEmpty())
                {
                    mapper.batchInsertShipments(bundle.shipments);
                    shipmentCount[0] += bundle.shipments.size();
                }
            }
        });

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("apiPath", API_PATH);
        result.put("syncMode", syncMode);
        result.put("shipmentId", shipmentId);
        result.put("dateBegin", dateBegin.format(DATE));
        result.put("dateEnd", dateEnd.format(DATE));
        result.put("dateType", 1);
        result.put("pageSize", PAGE_SIZE);
        result.put("fetchedPages", fetchedPages);
        result.put("remoteTotal", remoteTotal);
        result.put("savedPlans", bundles.size());
        result.put("savedItems", itemCount[0]);
        result.put("savedShipments", shipmentCount[0]);
        result.put("inboundPlanIds", inboundPlanIds);
        result.put("durationMs", System.currentTimeMillis() - startedAt);
        return result;
    }

    private PlanBundle toBundle(
            Map<String, Object> record, String queryShipmentId) throws Exception
    {
        LocalDateTime now = LocalDateTime.now();
        LingxingStaInboundPlan plan = new LingxingStaInboundPlan();
        String recordKey = deriveRecordKey(record);
        plan.setRecordKey(recordKey);
        plan.setInboundPlanId(textValue(firstText(
                record.get("inboundPlanId"), record.get("inbound_plan_id"))));
        plan.setSid(longValue(record.get("sid")));
        plan.setPlanName(textValue(firstText(
                record.get("planName"), record.get("plan_name"))));
        plan.setStatus(textValue(record.get("status")));
        Integer positionType = integerValue(record.get("positionType"));
        plan.setPositionType(positionType != null
                ? positionType : integerValue(record.get("position_type")));
        plan.setGmtCreate(dateTimeValue(firstText(
                record.get("gmtCreate"), record.get("gmt_create"))));
        plan.setGmtModified(dateTimeValue(firstText(
                record.get("gmtModified"), record.get("gmt_modified"))));
        plan.setSyncTime(now);
        plan.setCreateTime(now);
        plan.setUpdateTime(now);

        List<LingxingStaInboundPlanItem> items = new ArrayList<>();
        List<Map<String, Object>> sourceItems =
                listValue(firstNonNull(
                        record.get("inboundPlanItemList"),
                        record.get("inbound_plan_item_list")));
        for (int index = 0; index < sourceItems.size(); index++)
        {
            Map<String, Object> source = sourceItems.get(index);
            LingxingStaInboundPlanItem item = new LingxingStaInboundPlanItem();
            item.setRecordKey(recordKey);
            item.setInboundPlanId(plan.getInboundPlanId());
            item.setItemIndex(index + 1);
            item.setAsin(textValue(source.get("asin")));
            item.setFnsku(textValue(source.get("fnsku")));
            item.setMsku(textValue(source.get("msku")));
            item.setParentAsin(textValue(source.get("parentAsin")));
            item.setProductName(textValue(source.get("productName")));
            item.setQuantity(integerValue(source.get("quantity")));
            item.setSku(textValue(source.get("sku")));
            item.setTitle(textValue(source.get("title")));
            item.setUrl(textValue(source.get("url")));
            item.setCreateTime(now);
            item.setUpdateTime(now);
            items.add(item);
        }

        List<LingxingStaInboundPlanShipment> shipments = new ArrayList<>();
        List<Map<String, Object>> sourceShipments = listValue(firstNonNull(
                record.get("shipmentList"), record.get("shipment_list")));
        for (int index = 0; index < sourceShipments.size(); index++)
        {
            Map<String, Object> source = sourceShipments.get(index);
            LingxingStaInboundPlanShipment shipment =
                    new LingxingStaInboundPlanShipment();
            shipment.setRecordKey(recordKey);
            shipment.setInboundPlanId(plan.getInboundPlanId());
            shipment.setShipmentIndex(index + 1);
            shipment.setShipmentId(textValue(firstText(
                    source.get("shipmentId"), source.get("shipment_id"))));
            shipment.setShipmentConfirmationId(
                    textValue(firstText(
                            source.get("shipmentConfirmationId"),
                            source.get("shipment_confirmation_id"))));
            shipment.setCreateTime(now);
            shipment.setUpdateTime(now);
            shipments.add(shipment);
        }
        return new PlanBundle(plan, items, shipments);
    }

    private String deriveRecordKey(Map<String, Object> record)
    {
        String inboundPlanId = textValue(firstText(
                record.get("inboundPlanId"), record.get("inbound_plan_id")));
        if (inboundPlanId != null) return "PLAN:" + inboundPlanId;

        List<Map<String, Object>> shipments = listValue(firstNonNull(
                record.get("shipmentList"), record.get("shipment_list")));
        for (Map<String, Object> shipment : shipments)
        {
            String shipmentNo = textValue(firstText(
                    shipment.get("shipmentConfirmationId"),
                    shipment.get("shipment_confirmation_id"),
                    shipment.get("shipmentId"),
                    shipment.get("shipment_id")));
            if (shipmentNo != null) return "SHIPMENT:" + shipmentNo;
        }

        String fingerprint = firstText(record.get("sid")) + "|"
                + firstText(record.get("planName"), record.get("plan_name")) + "|"
                + firstText(record.get("gmtCreate"), record.get("gmt_create"));
        return "NO_SHIPMENT:" + sha256(fingerprint);
    }

    private String sha256(String value)
    {
        try
        {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8));
            StringBuilder result = new StringBuilder(digest.length * 2);
            for (byte b : digest) result.append(String.format("%02x", b));
            return result.toString();
        }
        catch (Exception e)
        {
            throw new IllegalStateException("生成STA记录关联键失败", e);
        }
    }

    private Object firstNonNull(Object... values)
    {
        for (Object value : values)
            if (value != null) return value;
        return null;
    }

    private void validateResponse(Map<String, Object> response)
    {
        if (response == null)
            throw new IllegalStateException("领星STA任务列表接口返回空响应");
        Integer code = integerValue(response.get("code"));
        if (code == null || code != 0)
            throw new IllegalStateException("领星STA任务列表接口失败，code=" + code
                    + "，message=" + firstText(response.get("message"), response.get("errorDetails")));
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> mapValue(Object value)
    {
        if (value instanceof Map<?, ?>) return (Map<String, Object>) value;
        if (value == null) return new LinkedHashMap<>();
        return objectMapper.convertValue(value,
                new TypeReference<Map<String, Object>>() {});
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> listValue(Object value)
    {
        if (value instanceof List<?>) return (List<Map<String, Object>>) value;
        if (value == null) return new ArrayList<>();
        return objectMapper.convertValue(value,
                new TypeReference<List<Map<String, Object>>>() {});
    }

    private String textValue(Object value)
    {
        String text = value == null ? null : String.valueOf(value).trim();
        return StringUtils.hasText(text) ? text : null;
    }

    private Integer integerValue(Object value)
    {
        String text = textValue(value);
        if (text == null) return null;
        try { return new BigDecimal(text).intValueExact(); }
        catch (Exception ignored) { return null; }
    }

    private Long longValue(Object value)
    {
        String text = textValue(value);
        if (text == null) return null;
        try { return new BigDecimal(text).longValueExact(); }
        catch (Exception ignored) { return null; }
    }

    private LocalDateTime dateTimeValue(Object value)
    {
        String text = textValue(value);
        if (text == null) return null;
        for (DateTimeFormatter formatter : DATE_TIMES)
        {
            try { return LocalDateTime.parse(text, formatter); }
            catch (DateTimeParseException ignored) { }
        }
        return null;
    }

    private String firstText(Object... values)
    {
        for (Object value : values)
        {
            String text = textValue(value);
            if (text != null) return text;
        }
        return "";
    }

    private String trim(String value)
    {
        return value == null ? null : value.trim();
    }

    private record PlanBundle(
            LingxingStaInboundPlan plan,
            List<LingxingStaInboundPlanItem> items,
            List<LingxingStaInboundPlanShipment> shipments)
    {
    }
}
