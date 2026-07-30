package com.ruoyi.system.service.operation.external.lingxing;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import java.math.BigDecimal;
import java.time.YearMonth;
import java.time.ZoneId;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

/**
 * 领星“查询FBA库存列表-v2”月度全量快照。
 *
 * <p>不传业务筛选条件，只使用接口必需的分页参数。相同拉取年月整月覆盖，
 * 不同年月保留历史。</p>
 */
@Service
public class AmzFbaInventorySnapshotSyncService
{
    private static final Logger LOG =
            LoggerFactory.getLogger(AmzFbaInventorySnapshotSyncService.class);
    private static final String API =
            "basicOpen/openapi/storage/fbaWarehouseDetail";
    private static final int PAGE_SIZE = 200;
    private static final int MAX_PAGES = 10000;
    private static final int PARTIAL_PAGE_RETRIES = 2;
    private static final long PAGE_INTERVAL_MS = 1100L;
    private static final ZoneId BUSINESS_ZONE = ZoneId.of("Asia/Shanghai");

    private final LingxingGatewayService gateway;
    private final ObjectMapper objectMapper;
    private final AmzFbaInventorySnapshotReplaceService replaceService;

    public AmzFbaInventorySnapshotSyncService(
            LingxingGatewayService gateway,
            ObjectMapper objectMapper,
            AmzFbaInventorySnapshotReplaceService replaceService)
    {
        this.gateway = gateway;
        this.objectMapper = objectMapper;
        this.replaceService = replaceService;
    }

    public OperationSyncResult syncCurrentMonth() throws Exception
    {
        long startedAt = System.currentTimeMillis();
        String pullMonth = YearMonth.now(BUSINESS_ZONE).toString();
        String syncBatchId = UUID.randomUUID().toString();
        List<Map<String, Object>> remoteRows = fetchAll();
        if (remoteRows.isEmpty())
            throw new IllegalStateException(
                    "领星FBA库存接口全量返回0条，拒绝覆盖" + pullMonth + "原快照");

        List<Map<String, Object>> rows = new ArrayList<>(remoteRows.size());
        for (Map<String, Object> remoteRow : remoteRows)
            rows.add(toDatabaseRow(
                    remoteRow, pullMonth, syncBatchId));

        int inserted = replaceService.replaceMonth(pullMonth, rows);
        return OperationSyncResult.success(
                "amz_fba_inventory_snapshot",
                "领星-Amazon FBA库存月度快照",
                API,
                remoteRows.size(),
                inserted,
                System.currentTimeMillis() - startedAt);
    }

    private List<Map<String, Object>> fetchAll() throws Exception
    {
        List<Map<String, Object>> allRows = new ArrayList<>();
        int offset = 0;
        int expectedTotal = -1;
        boolean completed = false;

        for (int page = 0; page < MAX_PAGES; page++)
        {
            Map<String, Object> body = new LinkedHashMap<>();
            body.put("offset", offset);
            body.put("length", PAGE_SIZE);
            // 该开关用于取得欧洲共享仓的完整嵌套库存字段，不属于业务筛选条件。
            body.put("query_fba_storage_quantity_list", true);

            Map<String, Object> response = gateway.post(API, body);
            validateResponse(response);
            List<Map<String, Object>> batch = list(response.get("data"));
            int responseTotal = integer(response.get("total"), -1);
            if (responseTotal >= 0) expectedTotal = responseTotal;

            if (batch.isEmpty())
            {
                completed = true;
                break;
            }

            // 库存列表在长时间翻页期间会动态增删，接口total并不是快照值。
            // 对不足一页的数据原页重试，排除偶发截断；稳定后以短页作为结束标志。
            if (batch.size() < PAGE_SIZE)
            {
                for (int retry = 1;
                        retry <= PARTIAL_PAGE_RETRIES && batch.size() < PAGE_SIZE;
                        retry++)
                {
                    Thread.sleep(PAGE_INTERVAL_MS);
                    Map<String, Object> retryResponse = gateway.post(API, body);
                    validateResponse(retryResponse);
                    List<Map<String, Object>> retryBatch =
                            list(retryResponse.get("data"));
                    int retryTotal = integer(retryResponse.get("total"), -1);
                    if (retryTotal >= 0) expectedTotal = retryTotal;
                    if (retryBatch.size() > batch.size())
                        batch = retryBatch;
                }
            }

            allRows.addAll(batch);
            if (batch.size() < PAGE_SIZE)
            {
                completed = true;
                break;
            }

            offset += PAGE_SIZE;
            Thread.sleep(PAGE_INTERVAL_MS);
        }

        if (!completed)
            throw new IllegalStateException(
                    "领星FBA库存超过最大分页限制：" + MAX_PAGES + "页");
        if (expectedTotal >= 0 && expectedTotal != allRows.size())
            LOG.warn("领星FBA库存分页期间total发生变化或存在延迟：接口报告{}条，"
                            + "按分页结束标志实际取得{}条，本次按实际数据生成月度快照",
                    expectedTotal, allRows.size());
        return allRows;
    }

    private void validateResponse(Map<String, Object> response)
    {
        if (response == null)
            throw new IllegalStateException("领星FBA库存接口返回为空");
        if (integer(response.get("code"), -1) != 0)
            throw new IllegalStateException("领星FBA库存接口失败：code="
                    + text(response.get("code")) + "，message="
                    + text(response.get("message")) + "，error_details="
                    + text(response.get("error_details")));
        if (!(response.get("data") instanceof List<?>))
            throw new IllegalStateException("领星FBA库存接口data不是数组");
    }

    private Map<String, Object> toDatabaseRow(
            Map<String, Object> source,
            String pullMonth,
            String syncBatchId) throws Exception
    {
        Map<String, Object> row = new LinkedHashMap<>();
        row.put("pull_month", pullMonth);
        row.put("name", string(source, "name"));
        row.put("storage_type_name", string(source, "storage_type_name"));
        row.put("seller_group_name", string(source, "seller_group_name"));
        row.put("sid", decimal(source, "sid"));
        row.put("asin", string(source, "asin"));
        row.put("asin_principal_list_json", json(source.get("asin_principal_list")));
        row.put("product_name", string(source, "product_name"));
        row.put("small_image_url", string(source, "small_image_url"));
        row.put("seller_sku", string(source, "seller_sku"));
        row.put("fnsku", string(source, "fnsku"));
        row.put("sku", string(source, "sku"));
        row.put("category_text", string(source, "category_text"));
        row.put("cid", decimal(source, "cid"));
        row.put("product_brand_text", string(source, "product_brand_text"));
        row.put("bid", decimal(source, "bid"));
        row.put("share_type", decimal(source, "share_type"));

        for (String field : NUMERIC_FIELDS)
            row.put(field, decimal(source, field));
        for (String field : STRING_VALUE_FIELDS)
            row.put(field, string(source, field));

        row.put("recommended_action", string(source, "recommended_action"));
        row.put("fba_inventory_level_health_status",
                string(source, "fba_inventory_level_health_status"));
        row.put("low_inventory_level_fee_applied",
                string(source, "low_inventory_level_fee_applied"));
        row.put("fulfillment_channel", string(source, "fulfillment_channel"));
        row.put("fba_storage_quantity_list_json",
                json(source.get("fba_storage_quantity_list")));
        row.put("raw_json", objectMapper.writeValueAsString(source));
        row.put("sync_batch_id", syncBatchId);
        return row;
    }

    private static final List<String> NUMERIC_FIELDS = List.of(
            "total", "total_price", "available_total",
            "afn_fulfillable_quantity", "afn_reserved_quantity",
            "reserved_fc_transfers", "reserved_fc_processing",
            "reserved_customerorders", "quantity",
            "afn_unsellable_quantity",
            "afn_inbound_working_quantity",
            "afn_inbound_shipped_quantity",
            "afn_inbound_receiving_quantity",
            "stock_up_num", "afn_researching_quantity",
            "total_fulfillable_quantity", "inv_age_0_to_30_days",
            "inv_age_31_to_60_days", "inv_age_61_to_90_days",
            "inv_age_0_to_90_days", "inv_age_91_to_180_days",
            "inv_age_181_to_270_days", "inv_age_271_to_330_days",
            "inv_age_271_to_365_days", "inv_age_331_to_365_days",
            "inv_age_365_plus_days",
            "sell_through", "estimated_excess_quantity",
            "estimated_storage_cost_next_month",
            "fba_minimum_inventory_level", "historical_days_of_supply",
            "warehouse_damaged_quantity",
            "customer_damaged_quantity", "carrier_damaged_quantity",
            "distributor_damaged_quantity", "defective_quantity",
            "expired_quantity");

    /** 接口文档定义为 string，必须原样保存，不能假设一定是数字。 */
    private static final List<String> STRING_VALUE_FIELDS = List.of(
            "available_total_price", "afn_fulfillable_quantity_price",
            "afn_reserved_quantity_price", "reserved_fc_transfers_price",
            "reserved_fc_processing_price", "reserved_customerorders_price",
            "quantity_price", "afn_unsellable_quantity_price",
            "afn_inbound_working_quantity_price",
            "afn_inbound_shipped_quantity_price",
            "afn_inbound_receiving_quantity_price", "stock_up_num_price",
            "afn_researching_quantity_price", "inv_age_0_to_30_price",
            "inv_age_31_to_60_price", "inv_age_61_to_90_price",
            "inv_age_0_to_90_price", "inv_age_91_to_180_price",
            "inv_age_181_to_270_price", "inv_age_271_to_330_price",
            "inv_age_271_to_365_price", "inv_age_331_to_365_price",
            "inv_age_365_plus_price", "historical_days_of_supply_price",
            "cg_price", "cg_transport_costs");

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> list(Object value)
    {
        if (value instanceof List<?>)
            return objectMapper.convertValue(
                    value, new TypeReference<List<Map<String, Object>>>() {});
        return new ArrayList<>();
    }

    private String json(Object value) throws Exception
    {
        return objectMapper.writeValueAsString(
                value == null ? List.of() : value);
    }

    private String string(Map<String, Object> source, String key)
    {
        Object value = source.get(key);
        String text = value == null ? "" : String.valueOf(value).trim();
        return text.isEmpty() ? null : text;
    }

    private BigDecimal decimal(Map<String, Object> source, String key)
    {
        Object value = source.get(key);
        String text = value == null ? "" : String.valueOf(value).trim();
        if (text.isEmpty() || "-".equals(text)) return null;
        try
        {
            return new BigDecimal(text.replace(",", "")
                    .replace("￥", "").replace("¥", "")
                    .replace("$", "").replace("%", "").trim());
        }
        catch (Exception e)
        {
            throw new IllegalArgumentException(
                    "领星FBA库存字段" + key + "不是有效数字：" + text, e);
        }
    }

    private int integer(Object value, int defaultValue)
    {
        if (value instanceof Number) return ((Number) value).intValue();
        try { return Integer.parseInt(text(value)); }
        catch (Exception ignored) { return defaultValue; }
    }

    private String text(Object value)
    {
        return value == null ? "" : String.valueOf(value).trim();
    }
}
