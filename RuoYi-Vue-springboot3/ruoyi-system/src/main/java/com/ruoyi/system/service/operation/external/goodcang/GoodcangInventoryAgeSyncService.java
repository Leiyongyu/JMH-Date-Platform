package com.ruoyi.system.service.operation.external.goodcang;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.system.mapper.operation.external.GoodcangInventoryAgeSnapshotMapper;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import java.time.LocalDateTime;
import java.time.YearMonth;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

/** 谷仓eBay库存库龄月度原始数据全量同步。 */
@Service
public class GoodcangInventoryAgeSyncService
{
    private static final Logger LOG = LoggerFactory.getLogger(
            GoodcangInventoryAgeSyncService.class);
    private static final String API = "/inventory/inventory_age_list";
    private static final int PAGE_SIZE = 200;
    private static final int BATCH_SIZE = 500;
    private static final int MAX_PAGES = 10000;

    private final GoodcangClient client;
    private final GoodcangInventoryAgeSnapshotMapper mapper;
    private final ObjectMapper objectMapper;
    private final TransactionTemplate transactionTemplate;

    public GoodcangInventoryAgeSyncService(
            GoodcangClient client,
            GoodcangInventoryAgeSnapshotMapper mapper,
            ObjectMapper objectMapper,
            PlatformTransactionManager transactionManager)
    {
        this.client = client;
        this.mapper = mapper;
        this.objectMapper = objectMapper;
        this.transactionTemplate = new TransactionTemplate(transactionManager);
    }

    public OperationSyncResult syncCurrentMonth() throws Exception
    {
        long started = System.currentTimeMillis();
        String snapshotMonth = YearMonth.now().toString();
        String batchId = UUID.randomUUID().toString().replace("-", "");
        LocalDateTime pulledAt = LocalDateTime.now();
        List<Map<String, Object>> rows = new ArrayList<>();
        long expectedTotal = -1L;

        for (int page = 1; page <= MAX_PAGES; page++)
        {
            Map<String, Object> response = client.getInventoryAgeList(
                    page, PAGE_SIZE);
            ensureSuccess(response);
            Map<String, Object> data = map(response.get("data"));
            if (data == null)
                throw new IllegalStateException("谷仓库龄接口data不是对象");
            List<Map<String, Object>> pageRows = list(data.get("list"));
            long pageTotal = longValue(data.get("total"), -1L);
            if (pageTotal >= 0) expectedTotal = pageTotal;

            for (int index = 0; index < pageRows.size(); index++)
            {
                Map<String, Object> source = pageRows.get(index);
                Map<String, Object> row = new LinkedHashMap<>();
                row.put("snapshotMonth", snapshotMonth);
                row.put("warehouseCode", text(source.get("warehouse_code")));
                row.put("productSku", text(source.get("product_sku")));
                row.put("ibaQuantity", longValue(source.get("iba_quantity"), 0L));
                row.put("ibaFifoTime", text(source.get("iba_fifo_time")));
                row.put("ibaWarningAge", integer(source.get("iba_warning_age")));
                row.put("productTitle", text(source.get("product_title")));
                row.put("productTitleEn", text(source.get("product_title_en")));
                row.put("warehouseDesc", text(source.get("warehouse_desc")));
                row.put("warehouseAge", integer(source.get("warehouse_age")));
                row.put("expirationDate", text(source.get("expiration_date")));
                row.put("sourcePage", page);
                row.put("sourceRowNo", index + 1);
                row.put("apiCode", integer(response.get("code")));
                row.put("apiMessage", text(response.get("message")));
                row.put("apiTotal", pageTotal >= 0 ? pageTotal : null);
                row.put("syncBatchId", batchId);
                row.put("rawJson", objectMapper.writeValueAsString(source));
                row.put("pulledAt", pulledAt);
                rows.add(row);
            }

            if (pageRows.isEmpty()
                    || pageRows.size() < PAGE_SIZE
                    || (expectedTotal >= 0 && rows.size() >= expectedTotal))
                break;
            if (page == MAX_PAGES)
                throw new IllegalStateException("谷仓库龄接口超过最大分页数");
        }

        if (rows.isEmpty())
            throw new IllegalStateException(
                    "谷仓库龄接口返回0条，已拒绝覆盖当月快照");
        if (expectedTotal >= 0 && rows.size() < expectedTotal)
            throw new IllegalStateException(
                    "谷仓库龄分页不完整：应返回" + expectedTotal
                            + "条，实际" + rows.size() + "条");

        transactionTemplate.executeWithoutResult(status -> {
            mapper.deleteBySnapshotMonth(snapshotMonth);
            for (int from = 0; from < rows.size(); from += BATCH_SIZE)
                mapper.batchInsert(rows.subList(
                        from, Math.min(from + BATCH_SIZE, rows.size())));
        });

        OperationSyncResult result = OperationSyncResult.success(
                "goodcang_inventory_age_monthly",
                "谷仓-eBay库存库龄月快照",
                API,
                rows.size(),
                rows.size(),
                System.currentTimeMillis() - started);
        Map<String, Object> details = new LinkedHashMap<>();
        details.put("snapshot_month", snapshotMonth);
        details.put("sync_batch_id", batchId);
        details.put("api_total", expectedTotal);
        details.put("stored_rows", rows.size());
        result.setDetails(details);
        result.setBusinessSummary(
                "快照月份" + snapshotMonth + "；库存库龄"
                        + rows.size() + "条；批次" + batchId);
        LOG.info("谷仓库存库龄同步完成: month={}, rows={}",
                snapshotMonth, rows.size());
        return result;
    }

    private void ensureSuccess(Map<String, Object> response)
    {
        if (response == null || response.get("code") == null
                || integer(response.get("code")) != 0)
            throw new IllegalStateException(
                    "谷仓库龄接口失败: code="
                            + (response == null ? null : response.get("code"))
                            + ", message="
                            + (response == null ? null : response.get("message")));
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> map(Object value)
    {
        if (value instanceof Map<?, ?>) return (Map<String, Object>) value;
        return null;
    }

    private List<Map<String, Object>> list(Object value)
    {
        if (value == null) return new ArrayList<>();
        try
        {
            List<Map<String, Object>> rows = objectMapper.convertValue(
                    value,
                    new TypeReference<List<Map<String, Object>>>() {});
            return rows != null ? rows : new ArrayList<>();
        }
        catch (Exception ignored)
        {
            return new ArrayList<>();
        }
    }

    private int integer(Object value)
    {
        try { return Integer.parseInt(text(value)); }
        catch (Exception ignored) { return 0; }
    }

    private long longValue(Object value, long fallback)
    {
        try { return Long.parseLong(text(value)); }
        catch (Exception ignored) { return fallback; }
    }

    private String text(Object value)
    {
        return value == null ? null : String.valueOf(value).trim();
    }
}
