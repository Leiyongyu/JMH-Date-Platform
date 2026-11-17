package com.ruoyi.system.service.operation.external.lingxing;

import com.ruoyi.system.mapper.operation.external.LingxingProductProcurementSnapshotMapper;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.time.YearMonth;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.util.StringUtils;

/** 领星产品管理中采购价、供应商阶梯价和国家头程成本月度同步。 */
@Service
public class LingxingProductProcurementSyncService
{
    private static final Logger LOG = LoggerFactory.getLogger(
            LingxingProductProcurementSyncService.class);
    private static final String LIST_API =
            "erp/sc/routing/data/local_inventory/productList";
    private static final String DETAIL_API =
            "erp/sc/routing/data/local_inventory/batchGetProductInfo";
    private static final String API = LIST_API + " -> " + DETAIL_API;
    private static final int LIST_PAGE_SIZE = 1000;
    private static final int DETAIL_BATCH_SIZE = 100;
    private static final int MAX_LIST_PAGES = 1000;
    private static final int BATCH_SIZE = 500;
    private static final Pattern TRANSPORT_COST_KEY = Pattern.compile(
            "^([A-Z]{2})_cg_transport_costs$");

    private final LingxingGatewayService gateway;
    private final LingxingProductProcurementSnapshotMapper mapper;
    private final TransactionTemplate transactionTemplate;

    public LingxingProductProcurementSyncService(
            LingxingGatewayService gateway,
            LingxingProductProcurementSnapshotMapper mapper,
            PlatformTransactionManager transactionManager)
    {
        this.gateway = gateway;
        this.mapper = mapper;
        this.transactionTemplate = new TransactionTemplate(transactionManager);
    }

    public OperationSyncResult syncCurrentMonth() throws Exception
    {
        long started = System.currentTimeMillis();
        String snapshotMonth = YearMonth.now().toString();
        String batchId = UUID.randomUUID().toString().replace("-", "");
        LocalDateTime pulledAt = LocalDateTime.now();
        List<Map<String, Object>> catalog = fetchFullProductCatalog();

        List<Map<String, Object>> products = new ArrayList<>();
        List<Map<String, Object>> stepPrices = new ArrayList<>();
        List<Map<String, Object>> transportCosts = new ArrayList<>();
        for (int from = 0; from < catalog.size(); from += DETAIL_BATCH_SIZE)
        {
            List<Map<String, Object>> catalogBatch = catalog.subList(
                    from, Math.min(from + DETAIL_BATCH_SIZE, catalog.size()));
            List<String> productIds = new ArrayList<>();
            for (Map<String, Object> catalogRow : catalogBatch)
            {
                String productId = text(catalogRow.get("id"));
                if (!StringUtils.hasText(productId))
                    throw new IllegalStateException(
                            "领星产品列表存在没有id的记录: sku="
                                    + text(catalogRow.get("sku")));
                productIds.add(productId);
            }

            Map<String, Object> body = new LinkedHashMap<>();
            body.put("productIds", productIds);
            Map<String, Object> response = gateway.post(DETAIL_API, body);
            ensureSuccess(response, "产品ID批次" + productIds.get(0));
            List<Map<String, Object>> details = list(response.get("data"));
            ensureCompleteDetailBatch(productIds, details);
            for (Map<String, Object> data : details)
            {
                String sku = text(data.get("sku"));
                if (!StringUtils.hasText(sku))
                    throw new IllegalStateException(
                            "领星批量产品详情存在空SKU: id=" + data.get("id"));
                Map<String, Object> product = baseRow(
                        snapshotMonth, sku, batchId, pulledAt);
                product.put("cgPrice", decimal(data.get("cg_price")));
                products.add(product);
                extractStepPrices(
                        data, snapshotMonth, sku, batchId, pulledAt, stepPrices);
                extractTransportCosts(
                        data, snapshotMonth, sku, batchId, pulledAt,
                        transportCosts);
            }
            LOG.info("领星产品采购快照进度: {}/{}",
                    Math.min(from + DETAIL_BATCH_SIZE, catalog.size()),
                    catalog.size());
        }

        if (products.isEmpty())
            throw new IllegalStateException(
                    "领星产品详情返回0条，已拒绝覆盖当月快照");
        if (products.size() != catalog.size())
            throw new IllegalStateException(
                    "领星产品详情不完整：列表" + catalog.size()
                            + "条，详情" + products.size() + "条");

        transactionTemplate.executeWithoutResult(status -> {
            mapper.deleteStepPricesBySnapshotMonth(snapshotMonth);
            mapper.deleteTransportCostsBySnapshotMonth(snapshotMonth);
            mapper.deleteProductsBySnapshotMonth(snapshotMonth);
            insertProducts(products);
            insertStepPrices(stepPrices);
            insertTransportCosts(transportCosts);
        });

        OperationSyncResult result = OperationSyncResult.success(
                "lingxing_product_procurement_monthly",
                "领星-产品采购与头程成本月快照",
                API,
                catalog.size(),
                products.size(),
                System.currentTimeMillis() - started);
        Map<String, Object> details = new LinkedHashMap<>();
        details.put("snapshot_month", snapshotMonth);
        details.put("sync_batch_id", batchId);
        details.put("product_rows", products.size());
        details.put("step_price_rows", stepPrices.size());
        details.put("transport_cost_rows", transportCosts.size());
        result.setDetails(details);
        result.setBusinessSummary(
                "快照月份" + snapshotMonth + "；产品" + products.size()
                        + "条；阶梯价" + stepPrices.size()
                        + "条；国家头程成本" + transportCosts.size()
                        + "条；批次" + batchId);
        LOG.info(
                "领星产品采购快照完成: month={}, products={}, prices={}, costs={}",
                snapshotMonth, products.size(), stepPrices.size(),
                transportCosts.size());
        return result;
    }

    private List<Map<String, Object>> fetchFullProductCatalog()
            throws Exception
    {
        Map<String, Map<String, Object>> rowsById = new LinkedHashMap<>();
        long expectedTotal = -1L;
        for (int page = 0; page < MAX_LIST_PAGES; page++)
        {
            int offset = page * LIST_PAGE_SIZE;
            Map<String, Object> body = new LinkedHashMap<>();
            body.put("offset", offset);
            body.put("length", LIST_PAGE_SIZE);
            Map<String, Object> response = gateway.post(LIST_API, body);
            ensureSuccess(response, "产品列表offset=" + offset);
            long responseTotal = longValue(response.get("total"), -1L);
            if (responseTotal >= 0) expectedTotal = responseTotal;
            List<Map<String, Object>> pageRows = list(response.get("data"));
            for (Map<String, Object> row : pageRows)
            {
                String id = text(row.get("id"));
                if (!StringUtils.hasText(id))
                    throw new IllegalStateException(
                            "领星产品列表存在没有id的记录: offset=" + offset);
                rowsById.put(id, row);
            }
            LOG.info("领星产品列表进度: {}/{}",
                    rowsById.size(), expectedTotal);
            if (pageRows.isEmpty()
                    || pageRows.size() < LIST_PAGE_SIZE
                    || (expectedTotal >= 0 && rowsById.size() >= expectedTotal))
                break;
            if (page == MAX_LIST_PAGES - 1)
                throw new IllegalStateException("领星产品列表超过最大分页数");
        }
        if (rowsById.isEmpty())
            throw new IllegalStateException("领星产品列表返回0条");
        if (expectedTotal >= 0 && rowsById.size() != expectedTotal)
            throw new IllegalStateException(
                    "领星产品列表分页不完整：总数" + expectedTotal
                            + "条，实际去重" + rowsById.size() + "条");
        return new ArrayList<>(rowsById.values());
    }

    private void ensureCompleteDetailBatch(
            List<String> requestedIds,
            List<Map<String, Object>> details)
    {
        Set<String> returnedIds = new LinkedHashSet<>();
        for (Map<String, Object> detail : details)
        {
            String id = text(detail.get("id"));
            if (StringUtils.hasText(id)) returnedIds.add(id);
        }
        if (returnedIds.size() == requestedIds.size()
                && returnedIds.containsAll(requestedIds))
            return;
        for (String requestedId : requestedIds)
            if (!returnedIds.contains(requestedId))
                throw new IllegalStateException(
                        "领星批量产品详情缺少产品ID=" + requestedId);
        throw new IllegalStateException(
                "领星批量产品详情数量不匹配：请求"
                        + requestedIds.size() + "条，返回" + details.size() + "条");
    }

    private void extractStepPrices(
            Map<String, Object> data,
            String month,
            String sku,
            String batchId,
            LocalDateTime pulledAt,
            List<Map<String, Object>> target)
    {
        List<Map<String, Object>> suppliers = list(data.get("supplier_quote"));
        for (int supplierIndex = 0; supplierIndex < suppliers.size(); supplierIndex++)
        {
            List<Map<String, Object>> quotes = list(
                    suppliers.get(supplierIndex).get("quotes"));
            for (int quoteIndex = 0; quoteIndex < quotes.size(); quoteIndex++)
            {
                List<Map<String, Object>> prices = list(
                        quotes.get(quoteIndex).get("step_prices"));
                for (int priceIndex = 0; priceIndex < prices.size(); priceIndex++)
                {
                    BigDecimal price = decimal(prices.get(priceIndex).get("price"));
                    if (price == null) continue;
                    Map<String, Object> row = baseRow(
                            month, sku, batchId, pulledAt);
                    row.put("supplierIndex", supplierIndex);
                    row.put("quoteIndex", quoteIndex);
                    row.put("stepPriceIndex", priceIndex);
                    row.put("price", price);
                    target.add(row);
                }
            }
        }
    }

    private void extractTransportCosts(
            Map<String, Object> data,
            String month,
            String sku,
            String batchId,
            LocalDateTime pulledAt,
            List<Map<String, Object>> target)
    {
        List<Map<String, Object>> relations = list(
                data.get("product_logistics_relation"));
        for (int relationIndex = 0; relationIndex < relations.size(); relationIndex++)
        {
            for (Map.Entry<String, Object> entry
                    : relations.get(relationIndex).entrySet())
            {
                Matcher matcher = TRANSPORT_COST_KEY.matcher(entry.getKey());
                if (!matcher.matches()) continue;
                BigDecimal cost = decimal(entry.getValue());
                if (cost == null) continue;
                Map<String, Object> row = baseRow(
                        month, sku, batchId, pulledAt);
                row.put("relationIndex", relationIndex);
                row.put("countryCode", matcher.group(1));
                row.put("transportCost", cost);
                target.add(row);
            }
        }
    }

    private void insertProducts(List<Map<String, Object>> rows)
    {
        for (int from = 0; from < rows.size(); from += BATCH_SIZE)
            mapper.batchInsertProducts(rows.subList(
                    from, Math.min(from + BATCH_SIZE, rows.size())));
    }

    private void insertStepPrices(List<Map<String, Object>> rows)
    {
        for (int from = 0; from < rows.size(); from += BATCH_SIZE)
            mapper.batchInsertStepPrices(rows.subList(
                    from, Math.min(from + BATCH_SIZE, rows.size())));
    }

    private void insertTransportCosts(List<Map<String, Object>> rows)
    {
        for (int from = 0; from < rows.size(); from += BATCH_SIZE)
            mapper.batchInsertTransportCosts(rows.subList(
                    from, Math.min(from + BATCH_SIZE, rows.size())));
    }

    private void ensureSuccess(Map<String, Object> response, String context)
    {
        if (response == null || integer(response.get("code")) != 0)
            throw new IllegalStateException(
                    context + ", code="
                            + (response == null ? null : response.get("code"))
                            + ", message="
                            + (response == null ? null : response.get("message"))
                            + ", error_details="
                            + (response == null ? null
                            : response.get("error_details")));
    }

    private Map<String, Object> baseRow(
            String month,
            String sku,
            String batchId,
            LocalDateTime pulledAt)
    {
        Map<String, Object> row = new LinkedHashMap<>();
        row.put("snapshotMonth", month);
        row.put("sku", sku);
        row.put("syncBatchId", batchId);
        row.put("pulledAt", pulledAt);
        return row;
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> map(Object value)
    {
        return value instanceof Map<?, ?>
                ? (Map<String, Object>) value : null;
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> list(Object value)
    {
        return value instanceof List<?>
                ? (List<Map<String, Object>>) value : new ArrayList<>();
    }

    private BigDecimal decimal(Object value)
    {
        if (value == null || !StringUtils.hasText(String.valueOf(value)))
            return null;
        try { return new BigDecimal(String.valueOf(value).trim()); }
        catch (Exception ignored) { return null; }
    }

    private int integer(Object value)
    {
        try { return Integer.parseInt(text(value)); }
        catch (Exception ignored) { return -1; }
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
