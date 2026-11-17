package com.ruoyi.system.service.operation.external.lingxing;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.system.domain.operation.external.LingxingShipmentOrderMapping;
import com.ruoyi.system.mapper.operation.external.AmzFbaShipmentMapper;
import com.ruoyi.system.mapper.operation.external.LingxingShipmentOrderMappingMapper;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

/**
 * 使用 amz_fba_shipment 中的去重货件单号，查询领星发货单列表并建立
 * FBA货件单号(shipment_id) → 发货单号(shipment_sn) 映射。
 */
@Service
public class LingxingShipmentOrderMappingSyncService
{
    private static final Logger LOG =
            LoggerFactory.getLogger(LingxingShipmentOrderMappingSyncService.class);
    private static final String API_PATH =
            "erp/sc/routing/storage/shipment/getInboundShipmentList";
    private static final int SEARCH_BATCH_SIZE = 20;
    private static final int PAGE_SIZE = 20;
    private static final int MAX_PAGES_PER_BATCH = 100;
    private static final int INSERT_BATCH_SIZE = 500;
    private static final long RATE_LIMIT_DELAY_MS = 1100L;
    private static final int INCREMENTAL_DAYS = 3;
    private static final DateTimeFormatter DATE_TIME_FORMAT =
            DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");
    private static final DateTimeFormatter DATE_FORMAT =
            DateTimeFormatter.ofPattern("yyyy-MM-dd");

    private final LingxingGatewayService gateway;
    private final AmzFbaShipmentMapper fbaShipmentMapper;
    private final LingxingShipmentOrderMappingMapper mappingMapper;
    private final ObjectMapper objectMapper;

    public LingxingShipmentOrderMappingSyncService(
            LingxingGatewayService gateway,
            AmzFbaShipmentMapper fbaShipmentMapper,
            LingxingShipmentOrderMappingMapper mappingMapper,
            ObjectMapper objectMapper)
    {
        this.gateway = gateway;
        this.fbaShipmentMapper = fbaShipmentMapper;
        this.mappingMapper = mappingMapper;
        this.objectMapper = objectMapper;
    }

    public OperationSyncResult syncAll() throws Exception
    {
        long startedAt = System.currentTimeMillis();
        if (mappingMapper.countAll() > 0)
        {
            return syncRecentCreated(startedAt);
        }

        List<String> sourceIds = fbaShipmentMapper.selectDistinctShipmentIds();
        LOG.info("领星货件发货单映射表为空，执行首次全量同步，源货件数={}",
                sourceIds == null ? 0 : sourceIds.size());
        return syncShipmentIds(sourceIds, startedAt);
    }

    public OperationSyncResult syncByShipmentId(String shipmentId) throws Exception
    {
        if (!StringUtils.hasText(shipmentId))
            throw new IllegalArgumentException("货件单号不能为空");
        return syncShipmentIds(
                List.of(shipmentId.trim()), System.currentTimeMillis());
    }

    /**
     * 映射表已有数据时，仅拉取最近3个自然日创建的发货单。
     * 使用 time_type=2（创建时间），并按 shipment_id 唯一键覆盖更新。
     */
    private OperationSyncResult syncRecentCreated(long startedAt) throws Exception
    {
        LocalDate endDate = LocalDate.now();
        LocalDate startDate = endDate.minusDays(INCREMENTAL_DAYS - 1L);
        LinkedHashMap<String, LingxingShipmentOrderMapping> mappings =
                new LinkedHashMap<>();
        int offset = 0;
        int requestCount = 0;
        int orderCount = 0;
        Set<String> noRequestedIds = Set.of();
        Set<String> ignoredMatchedIds = new LinkedHashSet<>();

        for (int page = 0; page < MAX_PAGES_PER_BATCH; page++)
        {
            Map<String, Object> response = gateway.post(
                    API_PATH, buildRecentRequest(startDate, endDate, offset));
            requestCount++;
            validateResponse(response);

            Map<String, Object> data = mapValue(response.get("data"));
            List<Map<String, Object>> orders = mapList(data.get("list"));
            orderCount += orders.size();
            for (Map<String, Object> order : orders)
            {
                collectMappings(
                        order, mappings, noRequestedIds, ignoredMatchedIds);
            }

            Integer total = integerValue(data.get("total"));
            offset += orders.size();
            if (orders.isEmpty()
                    || (total != null && offset >= total)
                    || orders.size() < PAGE_SIZE)
            {
                break;
            }
            Thread.sleep(RATE_LIMIT_DELAY_MS);
        }

        int saved = saveMappings(mappings);
        LOG.info("领星货件发货单映射最近3天增量完成：日期={}~{}，发货单={}，映射={}，"
                        + "保存影响行={}，请求次数={}",
                startDate, endDate, orderCount, mappings.size(), saved, requestCount);
        return OperationSyncResult.successAllowEmpty(
                "lingxing_shipment_order_mapping",
                "领星-货件与发货单映射",
                API_PATH,
                orderCount,
                mappings.size(),
                System.currentTimeMillis() - startedAt);
    }

    private OperationSyncResult syncShipmentIds(
            List<String> sourceIds, long startedAt) throws Exception
    {
        if (sourceIds == null || sourceIds.isEmpty())
        {
            return OperationSyncResult.successAllowEmpty(
                    "lingxing_shipment_order_mapping",
                    "领星-货件与发货单映射",
                    API_PATH, 0, 0, System.currentTimeMillis() - startedAt);
        }

        LinkedHashMap<String, LingxingShipmentOrderMapping> mappings =
                new LinkedHashMap<>();
        Set<String> requestedIds = new LinkedHashSet<>(sourceIds);
        Set<String> matchedSourceIds = new LinkedHashSet<>();
        int requestCount = 0;

        for (int from = 0; from < sourceIds.size(); from += SEARCH_BATCH_SIZE)
        {
            List<String> searchIds = new ArrayList<>(sourceIds.subList(
                    from, Math.min(from + SEARCH_BATCH_SIZE, sourceIds.size())));
            int offset = 0;

            for (int page = 0; page < MAX_PAGES_PER_BATCH; page++)
            {
                Map<String, Object> body = buildRequest(searchIds, offset);
                Map<String, Object> response = gateway.post(API_PATH, body);
                requestCount++;
                validateResponse(response);

                Map<String, Object> data = mapValue(response.get("data"));
                List<Map<String, Object>> orders = mapList(data.get("list"));
                for (Map<String, Object> order : orders)
                {
                    collectMappings(order, mappings, requestedIds, matchedSourceIds);
                }

                Integer total = integerValue(data.get("total"));
                offset += orders.size();
                if (orders.isEmpty()
                        || (total != null && offset >= total)
                        || orders.size() < PAGE_SIZE)
                {
                    break;
                }
                Thread.sleep(RATE_LIMIT_DELAY_MS);
            }

            LOG.info("领星货件发货单映射已查询 {}/{} 个货件，当前匹配={}，请求次数={}",
                    Math.min(from + SEARCH_BATCH_SIZE, sourceIds.size()),
                    sourceIds.size(), matchedSourceIds.size(), requestCount);
            if (from + SEARCH_BATCH_SIZE < sourceIds.size())
            {
                Thread.sleep(RATE_LIMIT_DELAY_MS);
            }
        }

        if (!sourceIds.isEmpty() && matchedSourceIds.isEmpty())
        {
            throw new IllegalStateException(
                    "领星发货单列表未返回任何货件号映射，请检查 senior_search_list 查询参数");
        }

        int saved = saveMappings(mappings);

        if (matchedSourceIds.size() < sourceIds.size())
        {
            List<String> missing = new ArrayList<>();
            for (String shipmentId : sourceIds)
            {
                if (!matchedSourceIds.contains(shipmentId))
                {
                    missing.add(shipmentId);
                    if (missing.size() >= 20) break;
                }
            }
            LOG.warn("领星货件发货单映射有未匹配货件：匹配={}/{}，示例={}",
                    matchedSourceIds.size(), sourceIds.size(), missing);
        }

        LOG.info("领星货件发货单映射同步完成：源货件={}，匹配源货件={}，保存映射={}，请求次数={}",
                sourceIds.size(), matchedSourceIds.size(), saved, requestCount);
        return OperationSyncResult.success(
                "lingxing_shipment_order_mapping",
                "领星-货件与发货单映射",
                API_PATH,
                sourceIds.size(),
                matchedSourceIds.size(),
                System.currentTimeMillis() - startedAt);
    }

    private Map<String, Object> buildRequest(List<String> shipmentIds, int offset)
    {
        Map<String, Object> seniorSearch = new LinkedHashMap<>();
        seniorSearch.put("search_field", "shipment_id");
        seniorSearch.put("search_value", shipmentIds);

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("offset", offset);
        body.put("length", PAGE_SIZE);
        body.put("is_delete", 0);
        body.put("senior_search_list", List.of(seniorSearch));
        return body;
    }

    private Map<String, Object> buildRecentRequest(
            LocalDate startDate, LocalDate endDate, int offset)
    {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("time_type", 2);
        body.put("start_date", startDate.format(DATE_FORMAT));
        body.put("end_date", endDate.format(DATE_FORMAT));
        body.put("offset", offset);
        body.put("length", PAGE_SIZE);
        body.put("is_delete", 0);
        return body;
    }

    private int saveMappings(
            Map<String, LingxingShipmentOrderMapping> mappings)
    {
        List<LingxingShipmentOrderMapping> rows =
                new ArrayList<>(mappings.values());
        int saved = 0;
        for (int from = 0; from < rows.size(); from += INSERT_BATCH_SIZE)
        {
            saved += mappingMapper.batchUpsert(new ArrayList<>(rows.subList(
                    from, Math.min(from + INSERT_BATCH_SIZE, rows.size()))));
        }
        return saved;
    }

    private void collectMappings(
            Map<String, Object> order,
            Map<String, LingxingShipmentOrderMapping> mappings,
            Set<String> requestedIds,
            Set<String> matchedSourceIds)
    {
        String topShipmentSn = textValue(order.get("shipment_sn"));
        if (!StringUtils.hasText(topShipmentSn)) return;

        Long shipmentListId = longValue(order.get("id"));
        Integer orderStatus = integerValue(order.get("status"));
        Integer isDelete = integerValue(order.get("is_delete"));
        LocalDateTime remoteCreateTime = dateTimeValue(
                firstValue(order.get("gmt_create"), order.get("create_time")));
        LocalDateTime remoteUpdateTime = dateTimeValue(firstValue(
                order.get("gmt_modified"), order.get("update_time")));
        LocalDateTime now = LocalDateTime.now();

        for (Map<String, Object> relation : mapList(order.get("relate_list")))
        {
            String shipmentId = textValue(relation.get("shipment_id"));
            if (!StringUtils.hasText(shipmentId)) continue;
            String shipmentSn = firstText(
                    textValue(relation.get("shipment_sn")), topShipmentSn);
            if (!StringUtils.hasText(shipmentSn)) continue;

            LingxingShipmentOrderMapping entity =
                    new LingxingShipmentOrderMapping();
            entity.setShipmentId(shipmentId.trim());
            entity.setShipmentSn(shipmentSn.trim());
            entity.setShipmentListId(shipmentListId);
            entity.setSid(longValue(relation.get("sid")));
            entity.setStoreName(textValue(relation.get("sname")));
            entity.setOrderStatus(orderStatus);
            entity.setShipmentStatus(textValue(firstValue(
                    relation.get("shipment_status"), relation.get("status"))));
            entity.setIsDelete(isDelete == null ? 0 : isDelete);
            entity.setRemoteCreateTime(remoteCreateTime);
            entity.setRemoteUpdateTime(remoteUpdateTime);
            entity.setSyncTime(now);
            entity.setCreateTime(now);
            entity.setUpdateTime(now);

            LingxingShipmentOrderMapping current =
                    mappings.get(entity.getShipmentId());
            if (current == null || shouldReplace(current, entity))
            {
                mappings.put(entity.getShipmentId(), entity);
            }
            if (requestedIds.contains(entity.getShipmentId()))
            {
                matchedSourceIds.add(entity.getShipmentId());
            }
        }
    }

    private boolean shouldReplace(
            LingxingShipmentOrderMapping current,
            LingxingShipmentOrderMapping candidate)
    {
        int currentDeleted = current.getIsDelete() == null ? 0 : current.getIsDelete();
        int candidateDeleted = candidate.getIsDelete() == null ? 0 : candidate.getIsDelete();
        if (currentDeleted != candidateDeleted) return candidateDeleted < currentDeleted;

        LocalDateTime currentTime = current.getRemoteUpdateTime();
        LocalDateTime candidateTime = candidate.getRemoteUpdateTime();
        if (currentTime == null) return candidateTime != null;
        if (candidateTime != null && !candidateTime.equals(currentTime))
            return candidateTime.isAfter(currentTime);

        Long currentId = current.getShipmentListId();
        Long candidateId = candidate.getShipmentListId();
        return candidateId != null && (currentId == null || candidateId > currentId);
    }

    private void validateResponse(Map<String, Object> response)
    {
        if (response == null)
            throw new IllegalStateException("领星发货单列表接口返回空响应");
        Integer code = integerValue(response.get("code"));
        if (code == null || code != 0)
        {
            throw new IllegalStateException("领星发货单列表接口失败，code=" + code
                    + "，message=" + firstText(
                            textValue(response.get("message")),
                            textValue(response.get("error_details"))));
        }
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
    private List<Map<String, Object>> mapList(Object value)
    {
        if (value instanceof List<?>) return (List<Map<String, Object>>) value;
        if (value == null) return new ArrayList<>();
        return objectMapper.convertValue(value,
                new TypeReference<List<Map<String, Object>>>() {});
    }

    private Object firstValue(Object first, Object second)
    {
        return first != null ? first : second;
    }

    private String firstText(String first, String second)
    {
        return StringUtils.hasText(first) ? first : second;
    }

    private String textValue(Object value)
    {
        if (value == null) return null;
        String text = String.valueOf(value).trim();
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
        try { return LocalDateTime.parse(text, DATE_TIME_FORMAT); }
        catch (Exception ignored) { return null; }
    }
}
