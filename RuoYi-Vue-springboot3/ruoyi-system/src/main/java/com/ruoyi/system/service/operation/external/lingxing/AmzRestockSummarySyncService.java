package com.ruoyi.system.service.operation.external.lingxing;

import com.ruoyi.system.domain.operation.external.AmzRestockSummary;
import com.ruoyi.system.mapper.operation.external.ShopListMapper;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import java.math.BigDecimal;
import java.util.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.beans.factory.annotation.Value;
import java.util.concurrent.TimeUnit;

/** Preserve shared parent + country children, validate every shop batch, then publish atomically. */
@Service
public class AmzRestockSummarySyncService
{
    private static final Logger LOG = LoggerFactory.getLogger(AmzRestockSummarySyncService.class);
    private static final String API = "erp/sc/routing/restocking/analysis/getSummaryList";
    // Lingxing getSummaryList documents a maximum of 50 root records per page.
    private static final int PAGE_SIZE = 50;
    public static final int TIMEOUT_MINUTES = 90;
    // 0 queries the entire selected shop scope once, avoiding shared-parent overlap.
    @Value("${lingxing.restock.sid-batch-size:0}")
    private int sidBatchSize = 0;
    private final LingxingGatewayService gw;
    private final AmzRestockSummaryReplaceService replacement;
    private final ShopListMapper shops;

    public AmzRestockSummarySyncService(LingxingGatewayService gw,
            AmzRestockSummaryReplaceService replacement, ShopListMapper shops)
    { this.gw = gw; this.replacement = replacement; this.shops = shops; }

    public OperationSyncResult syncAll() throws Exception
    {
        long start = System.currentTimeMillis();
        long deadline = System.nanoTime() + TimeUnit.MINUTES.toNanos(TIMEOUT_MINUTES);
        if (sidBatchSize < 0) throw new IllegalArgumentException("补货建议店铺批次大小不能为负数");
        List<String> configured = shops.selectSidsByPlatform("10001", 1);
        if (configured == null || configured.isEmpty())
            throw new IllegalStateException("未找到有效Amazon店铺，保留原补货建议");
        Set<String> uniqueSids = new LinkedHashSet<>();
        for (String sid : configured)
        {
            Integer parsed = integer(sid, "店铺SID");
            if (parsed == null || parsed <= 0) throw new IllegalStateException("Amazon店铺SID无效，保留原数据");
            uniqueSids.add(parsed.toString());
        }
        List<String> sids = new ArrayList<>(uniqueSids);
        int batchSize = sidBatchSize == 0 ? sids.size() : sidBatchSize;
        LOG.info("Amazon补货建议开始：{}家店铺，每批{}家，每页{}条，最长{}分钟", sids.size(), batchSize, PAGE_SIZE, TIMEOUT_MINUTES);
        Map<String,AmzRestockSummary> collected = new LinkedHashMap<>();
        int completed = 0;
        for (int from = 0; from < sids.size(); from += batchSize)
        {
            List<String> batch = new ArrayList<>(sids.subList(from, Math.min(from + batchSize, sids.size())));
            Map<String,AmzRestockSummary> batchRows = fetchStableBatch(batch, deadline);
            for (AmzRestockSummary row : batchRows.values()) merge(collected, row);
            completed += batch.size();
            LOG.info("Amazon补货建议已完整拉取店铺 {}/{}，累计保留父子节点 {} 条",completed,sids.size(),collected.size());
        }
        checkDeadline(deadline);
        if (completed != sids.size() || collected.isEmpty())
            throw new IllegalStateException("Amazon补货建议全量校验未通过，保留原数据");
        LOG.info("Amazon补货建议拉取完成：父子节点去重后{}条，开始事务替换源表", collected.size());
        int rows = replacement.replaceAll(new ArrayList<>(collected.values()));
        LOG.info("Amazon补货建议同步完成：写入{}条，总耗时{}秒", rows, (System.currentTimeMillis()-start)/1000);
        return OperationSyncResult.success("amz_restock", "领星-Amazon补货建议", API, rows, rows, System.currentTimeMillis()-start);
    }

    private Map<String,AmzRestockSummary> fetchStableBatch(List<String> batch, long deadline) throws Exception
    {
        for (int attempt = 1; attempt <= 3; attempt++)
        {
            try { return fetchBatch(batch, deadline, attempt); }
            catch (PaginationChangedException ex)
            {
                if (attempt == 3) throw new IllegalStateException(ex.getMessage() + "；该批已从第一页读取3轮，保留原数据", ex);
                LOG.warn("{}；丢弃本批已读取页面，从第一页重新读取，第{}/3轮", ex.getMessage(), attempt + 1);
                Thread.sleep(1000L * attempt);
                checkDeadline(deadline);
            }
        }
        throw new IllegalStateException("无法完成Amazon补货建议分页");
    }

    private Map<String,AmzRestockSummary> fetchBatch(List<String> batch, long deadline, int attempt) throws Exception
    {
        // Never merge an unstable attempt into the final publication.
        Map<String,AmzRestockSummary> collected = new LinkedHashMap<>();
        int offset = 0;
        Integer expected = null;
        Set<String> pageRoots = new HashSet<>();
        long roundStarted = System.nanoTime();
        int page = 0;
        do
        {
            checkDeadline(deadline);
            Map<String,Object> body = new LinkedHashMap<>();
            body.put("data_type",2); body.put("mode",0);
            body.put("offset",offset); body.put("length",PAGE_SIZE); body.put("sid_list",batch);
            Map<String,Object> response = gw.post(API,body);
            checkDeadline(deadline);
            if (response == null || !Set.of("0","200","OK","SUCCESS").contains(String.valueOf(response.get("code")).toUpperCase(Locale.ROOT)))
                throw new IllegalStateException("Amazon补货建议接口返回失败，保留原数据");
            Integer total = integer(response.get("total"),"分页总数");
            if (total == null || total < 0 || expected != null && !expected.equals(total))
                throw new PaginationChangedException("Amazon补货建议分页总数" + (total == null ? "缺失" : "变化或无效")
                        + "；店铺SID=" + batch + "；offset=" + offset + "；首次total=" + expected + "；本页total=" + total);
            expected = total;
            List<Map<String,Object>> data = list(response.get("data"), "data");
            if (data.size() > PAGE_SIZE || offset + (long) data.size() > expected
                    || data.isEmpty() && offset < expected)
                throw new IllegalStateException("Amazon补货建议分页不完整，已读取" + offset + "/" + expected + "，保留原数据");
            for (Map<String,Object> item : data)
            {
                Map<String,Object> basic = map(item.get("basic_info"), "basic_info");
                String root = text(basic.get("hash_id"));
                if (root.isEmpty() || !pageRoots.add(root))
                    throw new IllegalStateException("Amazon补货建议分页重复或缺少标识，保留原数据");
                collectTree(collected,item,0);
            }
            offset += data.size();
            page++;
            if (page == 1 || page % 10 == 0 || offset == expected)
            {
                long seconds = TimeUnit.NANOSECONDS.toSeconds(System.nanoTime()-roundStarted);
                long remaining = offset == 0 ? 0 : seconds * (expected-offset) / offset;
                LOG.info("Amazon补货建议进度：店铺{}家，第{}轮，第{}页，主记录{}/{}，父子节点{}条，本轮耗时{}秒，预计剩余{}秒（不含重试/写库）",
                        batch.size(),attempt,page,offset,expected,collected.size(),seconds,remaining);
            }
        } while (offset < expected);
        return collected;
    }

    private static void checkDeadline(long deadline)
    {
        AmzRestockSummaryReplaceService.checkCancelled();
        if (System.nanoTime() >= deadline)
            throw new IllegalStateException("Amazon补货建议拉取超过" + TIMEOUT_MINUTES + "分钟，保留原数据");
    }

    private static final class PaginationChangedException extends IllegalStateException
    {
        private PaginationChangedException(String message) { super(message); }
    }

    private static void merge(Map<String,AmzRestockSummary> result, AmzRestockSummary row)
    {
        AmzRestockSummary previous = result.get(row.getHashId());
        if (previous != null && (!previous.getSid().equals(row.getSid())
                || !previous.getMsku().equals(row.getMsku()) || !previous.getNodeType().equals(row.getNodeType())))
            throw new IllegalStateException("Amazon补货建议节点标识冲突，保留原数据");
        result.put(row.getHashId(), row);
    }

    private void collectTree(Map<String,AmzRestockSummary> result, Map<String,Object> item, int depth)
    {
        if (depth > 10) throw new IllegalStateException("Amazon补货建议层级异常，保留原数据");
        Map<String,Object> basic = map(item.get("basic_info"), "basic_info");
        Integer node = integer(basic.get("node_type"),"node_type");
        Integer sid = integer(basic.get("sid"),"sid");
        String hash = text(basic.get("hash_id"));
        Set<String> mskus = new LinkedHashSet<>();
        for (Map<String,Object> value : list(basic.get("msku_fnsku_list"),"msku_fnsku_list"))
            if (!text(value.get("msku")).isEmpty()) mskus.add(text(value.get("msku")));
        if (node == null || !Set.of(1,2,3).contains(node) || sid == null || sid <= 0 || hash.isEmpty() || mskus.isEmpty())
            throw new IllegalStateException("Amazon补货建议节点关键字段缺失，保留原数据");
        // Parent aliases preserve the legacy replenishment key. Country/independent
        // nodes must identify one MSKU; never multiply a single aggregated sale across aliases.
        if (node != 1 && mskus.size() != 1)
            throw new IllegalStateException("Amazon站点销量节点包含多个不同MSKU，不能直接分摊，保留原数据");
        AmzRestockSummary row = new AmzRestockSummary();
        row.setHashId(hash); row.setSid(sid); row.setMsku(mskus.iterator().next()); row.setNodeType(node);
        Map<String,Object> qty = optionalMap(item.get("amazon_quantity_info"),"amazon_quantity_info");
        Map<String,Object> sales = optionalMap(item.get("sales_info"),"sales_info");
        row.setFbaSellable(integer(qty.get("amazon_quantity_valid"),"amazon_quantity_valid"));
        row.setFbaInbound(integer(qty.get("amazon_quantity_shipping"),"amazon_quantity_shipping"));
        row.setFbaReserved(integer(qty.get("afn_reserved_quantity"),"afn_reserved_quantity"));
        row.setSales7d(integer(sales.get("sales_total_7"),"sales_total_7"));
        row.setSales14d(integer(sales.get("sales_total_14"),"sales_total_14"));
        row.setSales30d(integer(sales.get("sales_total_30"),"sales_total_30"));
        row.setSales60d(integer(sales.get("sales_total_60"),"sales_total_60"));
        row.setAvgSales14d(decimal(sales.get("sales_avg_14"),"sales_avg_14"));
        row.setAvgSales30d(decimal(sales.get("sales_avg_30"),"sales_avg_30"));
        row.setAvgSales60d(decimal(sales.get("sales_avg_60"),"sales_avg_60"));
        merge(result, row);
        List<Map<String,Object>> children = list(item.get("item_list"),"item_list");
        for (Map<String,Object> child : children)
            collectTree(result,child,depth+1);
        // A nonzero shared total must be accounted for by country rows. FBA stock
        // is shared and must never be summed for this validation; only sales add up.
        if (node == 1 && row.getSales30d() != null && row.getSales30d() > 0)
        {
            long countrySales = 0;
            Set<String> counted = new HashSet<>();
            for (Map<String,Object> child : children)
            {
                String childHash = text(map(child.get("basic_info"),"basic_info").get("hash_id"));
                if (!counted.add(childHash)) continue;
                Integer value = result.get(childHash).getSales30d();
                if (value == null) throw new IllegalStateException("Amazon共享汇总缺少国家销量，保留原数据");
                countrySales += value;
            }
            if (countrySales != row.getSales30d())
                throw new IllegalStateException("Amazon共享汇总与国家销量合计不一致，保留原数据");
        }
    }

    @SuppressWarnings("unchecked")
    private static Map<String,Object> map(Object value,String field)
    {
        if (!(value instanceof Map)) throw new IllegalStateException("Amazon补货建议字段格式异常："+field);
        return (Map<String,Object>) value;
    }

    private static Map<String,Object> optionalMap(Object value,String field)
    { return value == null ? Map.of() : map(value,field); }

    private static List<Map<String,Object>> list(Object value,String field)
    {
        if (value == null) return List.of();
        if (!(value instanceof List<?> values)) throw new IllegalStateException("Amazon补货建议字段格式异常："+field);
        List<Map<String,Object>> rows = new ArrayList<>();
        for (Object entry : values) rows.add(map(entry,field));
        return rows;
    }

    private static String text(Object value) { return value == null ? "" : value.toString().trim(); }

    private static Integer integer(Object value,String field)
    {
        BigDecimal number = decimal(value,field);
        if (number == null) return null;
        try { return number.intValueExact(); }
        catch (ArithmeticException e) { throw new IllegalStateException("Amazon补货建议数值异常："+field); }
    }

    private static BigDecimal decimal(Object value,String field)
    {
        if (value == null || text(value).isEmpty()) return null;
        try { return new BigDecimal(text(value)); }
        catch (NumberFormatException e) { throw new IllegalStateException("Amazon补货建议数值异常："+field); }
    }
}
