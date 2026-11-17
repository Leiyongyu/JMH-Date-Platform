package com.ruoyi.system.service.procurement;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.common.core.redis.RedisCache;
import com.ruoyi.common.exception.ServiceException;
import com.ruoyi.system.mapper.procurement.PendingPurchaseStatusMapper;
import com.ruoyi.system.service.operation.IOperationSyncLogService;
import com.ruoyi.system.service.operation.external.lingxing.LingxingGatewayService;
import com.ruoyi.system.service.operation.sync.OperationSyncContext;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.*;
import java.util.concurrent.TimeUnit;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/** 独立的待采购状态快照，不改变共享 purchase_order 或待采购内部状态。 */
@Service
public class PendingPurchaseStatusService
{
    static final String API = "erp/sc/routing/data/local_inventory/purchaseOrderList";
    private static final String TYPE = "pending_purchase_status";
    private static final String NAME = "待采购-领星采购单状态";
    private static final Logger LOG = LoggerFactory.getLogger(PendingPurchaseStatusService.class);
    private static final String LOCK = "lock:sync:lingxing:ebay";
    private static final DateTimeFormatter TIME = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");
    private static final Map<String, String> WAREHOUSE_SITES = Map.of(
        "18674", "DE", "18699", "DE", "18675", "UK", "18702", "UK",
        "18676", "US", "18700", "US", "18701", "US");
    private final PendingPurchaseStatusMapper mapper;
    private final LingxingGatewayService gateway;
    private final ObjectMapper json;
    private final TransactionTemplate transaction;
    private final RedisCache redis;
    private final IOperationSyncLogService logs;

    public PendingPurchaseStatusService(PendingPurchaseStatusMapper mapper, LingxingGatewayService gateway,
            ObjectMapper json, TransactionTemplate transaction, RedisCache redis, IOperationSyncLogService logs)
    {
        this.mapper = mapper; this.gateway = gateway; this.json = json;
        this.transaction = transaction; this.redis = redis; this.logs = logs;
    }

    public Map<String, Object> state() { return mapper.selectState(); }

    public List<Map<String, Object>> summary(List<Long> ids)
    {
        if (ids == null || ids.isEmpty() || ids.size() > 500 || ids.stream().anyMatch(id -> id == null || id <= 0))
            throw new ServiceException("请选择1至500条有效待采购记录");
        return mapper.selectSummary(ids.stream().distinct().toList());
    }

    public List<Map<String, Object>> details(Long id)
    {
        if (id == null || id <= 0) throw new ServiceException("待采购记录ID无效");
        return mapper.selectDetails(id);
    }

    /** 手动任务和Quartz均在执行线程内持有同一分组锁；失败保留上次成功快照。 */
    public void sync(String trigger, String operator)
    {
        long started = System.currentTimeMillis();
        if (!redis.tryLock(LOCK, 3600))
        {
            OperationSyncResult skipped = OperationSyncResult.skipped(TYPE, NAME, API, "eBay同步正在执行，请稍后重试", 0);
            Long id = logs.start(TYPE, NAME, API, trigger, operator, null, null);
            logs.finish(id, skipped);
            OperationSyncContext.set(skipped);
            return;
        }
        Long logId = null;
        try
        {
            logId = logs.start(TYPE, NAME, API, trigger, operator, null, null);
            if (mapper.start() != 1) throw new IllegalStateException("同步元数据未初始化，请先执行新增表SQL");
            LocalDate to = LocalDate.now();
            LocalDate from = to.minusMonths(6);
            List<Map<String, Object>> rows = collect(from, to, System.nanoTime() + TimeUnit.MINUTES.toNanos(30));
            checkDeadline(started);
            transaction.executeWithoutResult(tx -> {
                mapper.clearSnapshot();
                for (int i = 0; i < rows.size(); i += 200)
                    mapper.insertRows(rows.subList(i, Math.min(i + 200, rows.size())));
                if (mapper.publish(from, to, rows.size()) != 1) throw new IllegalStateException("同步元数据未初始化");
            });
            OperationSyncResult result = OperationSyncResult.successAllowEmpty(TYPE, NAME, API, rows.size(), rows.size(), System.currentTimeMillis()-started);
            OperationSyncContext.set(result);
            // 业务事务已提交，日志失败不能把成功快照标为失败。
            try { logs.finish(logId, result); }
            catch (Exception e) { LOG.error("待采购状态快照已发布，同步日志写入失败: {}", e.getClass().getSimpleName()); }
        }
        catch (Exception e)
        {
            if (e instanceof InterruptedException) Thread.currentThread().interrupt();
            try { mapper.fail(); }
            catch (Exception stateError) { LOG.error("待采购状态同步失败，元数据写入失败: {}", stateError.getClass().getSimpleName()); }
            // 不把上游响应体（可能含敏感业务信息）回传给浏览器或告警。
            String message = "采购状态同步失败，保留上次成功数据；" + (e instanceof IllegalStateException ? e.getMessage() : e.getClass().getSimpleName());
            OperationSyncResult result = OperationSyncResult.failed(TYPE, NAME, API, message, System.currentTimeMillis()-started);
            if (logId != null) logs.finish(logId, result);
            OperationSyncContext.set(result);
            throw new ServiceException(message);
        }
        finally { redis.unlock(LOCK); }
    }

    private static void checkDeadline(long started)
    {
        if (Thread.currentThread().isInterrupted() || System.currentTimeMillis()-started >= TimeUnit.MINUTES.toMillis(30))
            throw new IllegalStateException("超过30分钟，未发布本次数据");
    }

    List<Map<String, Object>> collect(LocalDate from, LocalDate to, long deadline) throws Exception
    {
        Set<String> skus = new HashSet<>(mapper.selectSkus());
        Map<String, String> warehouses = new HashMap<>();
        for (Map<String, Object> w : mapper.selectWarehouses()) warehouses.put(text(w, "wid"), text(w, "name"));
        Map<String, Map<String, Object>> result = new LinkedHashMap<>();
        if (skus.isEmpty()) return new ArrayList<>();
        Set<String> seenOrders = new HashSet<>();
        long nextCall = 0;
        for (LocalDate start = from; !start.isAfter(to);)
        {
            LocalDate end = start.plusDays(29).isAfter(to) ? to : start.plusDays(29);
            int offset = 0;
            Long expectedTotal = null;
            while (true)
            {
                if (Thread.currentThread().isInterrupted() || System.nanoTime() >= deadline)
                    throw new IllegalStateException("超过30分钟，未发布本次数据");
                long delay = nextCall - System.nanoTime();
                if (delay > 0) TimeUnit.NANOSECONDS.sleep(delay);
                Map<String, Object> response;
                try
                {
                    response = gateway.post(API, Map.of("start_date", start.toString(), "end_date", end.toString(),
                        "search_field_time", "create_time", "offset", offset, "length", 500));
                }
                catch (Exception e)
                {
                    if (e instanceof InterruptedException) Thread.currentThread().interrupt();
                    var http = java.util.regex.Pattern.compile("Lingxing HTTP ([0-9]{3})").matcher(Objects.toString(e.getMessage(), ""));
                    String reason = http.find() ? "HTTP " + http.group(1) : e.getClass().getSimpleName();
                    throw new IllegalStateException("领星采购单请求失败(" + reason + ")，请稍后重试");
                }
                nextCall = System.nanoTime() + TimeUnit.SECONDS.toNanos(1);
                if (response == null || !"0".equals(text(response, "code")))
                    throw new IllegalStateException("领星采购单接口返回失败，code=" +
                        (response != null && text(response,"code").matches("-?[0-9]+") ? text(response,"code") : "未提供"));
                List<Map<String, Object>> orders = objects(response.get("data"));
                if (orders.size() > 500) throw new IllegalStateException("采购单返回条数超过请求分页大小");
                String totalText = text(response, "total");
                if (!totalText.isEmpty())
                {
                    long total = Long.parseLong(totalText);
                    if (total < offset + orders.size() || (expectedTotal != null && total != expectedTotal))
                        throw new IllegalStateException("采购单分页总数变化或不足，未发布本次数据");
                    expectedTotal = total;
                }
                for (Map<String, Object> order : orders)
                {
                    String sn = text(order, "order_sn");
                    if (sn.isEmpty() || !seenOrders.add(sn)) throw new IllegalStateException("采购单号缺失或分页重复");
                    LocalDateTime created = dateTime(text(order, "create_time"));
                    if (created == null || created.toLocalDate().isBefore(start) || created.toLocalDate().isAfter(end))
                        throw new IllegalStateException("采购单创建时间不在请求范围");
                    for (Map<String, Object> item : objects(order.get("item_list")))
                    {
                        if ("1".equals(text(item, "is_delete"))) continue;
                        String sku = text(item, "sku").toUpperCase(Locale.ROOT);
                        if (!skus.contains(sku)) continue;
                        // 明细wid存在时禁止使用另一仓库的主单名称。
                        String wid = text(item, "wid");
                        boolean itemWarehouse = !wid.isEmpty() && !"0".equals(wid);
                        if (!itemWarehouse) wid = text(order, "wid");
                        String warehouse = text(item, "ware_house_name");
                        if (warehouse.isEmpty()) warehouse = warehouses.getOrDefault(wid, "");
                        if (warehouse.isEmpty() && !itemWarehouse) warehouse = text(order, "ware_house_name");
                        String site = warehouseSite(wid, warehouse);
                        if (site == null) continue;
                        String itemId = text(item, "id");
                        if (itemId.isEmpty()) throw new IllegalStateException("采购单商品明细ID缺失");
                        Map<String, Object> row = new HashMap<>();
                        row.put("orderSn", sn); row.put("itemId", itemId); row.put("sku", sku); row.put("site", site);
                        row.put("wid", wid); row.put("warehouseName", warehouse); row.put("supplierName", text(order, "supplier_name"));
                        row.put("orderStatus", status(order, "status", "status_text", Map.of("-1","作废","3","待提交","1","待下单","2","待到货","9","完成","121","待审核","122","驳回","124","作废")));
                        row.put("arrivalStatus", status(order, "status_shipped", "status_shipped_text", Map.of("1","未到货","2","部分到货","3","全部到货")));
                        row.put("payStatus", status(order, "pay_status", "pay_status_text", Map.of("0","未申请","1","已申请","2","部分付款","3","已付款")));
                        row.put("quantityReal", number(item, "quantity_real")); row.put("quantityEntry", number(item, "quantity_entry"));
                        row.put("quantityReceive", number(item, "quantity_receive"));
                        row.put("sourceCreated", created); row.put("sourceUpdated", dateTime(text(order, "update_time")));
                        Map<String, Object> header = new LinkedHashMap<>(order); header.remove("item_list");
                        row.put("rawJson", json.writeValueAsString(Map.of("order", header, "item", item)));
                        if (result.putIfAbsent(sn + "|" + itemId, row) != null) throw new IllegalStateException("采购单商品明细重复");
                    }
                }
                offset += orders.size();
                if (expectedTotal != null && offset == expectedTotal) break;
                if (orders.size() < 500)
                {
                    if (expectedTotal != null && offset != expectedTotal) throw new IllegalStateException("采购单分页提前结束");
                    break;
                }
            }
            start = end.plusDays(1);
        }
        return new ArrayList<>(result.values());
    }

    static String warehouseSite(String wid, String name)
    {
        if (WAREHOUSE_SITES.containsKey(wid)) return WAREHOUSE_SITES.get(wid);
        String n = name.toUpperCase(Locale.ROOT);
        if (!n.contains("EBAY") && !Set.of("19578", "19579").contains(wid)) return null;
        if (n.contains("德国") || n.matches(".*(?:^|[^A-Z])DE(?:[^A-Z]|$).*")) return "DE";
        if (n.contains("英国") || n.matches(".*(?:^|[^A-Z])(?:UK|GB)(?:[^A-Z]|$).*")) return "UK";
        if (n.contains("美国") || n.matches(".*(?:^|[^A-Z])US(?:[^A-Z]|$).*")) return "US";
        return "UNKNOWN";
    }

    private static String status(Map<String, Object> m, String codeKey, String textKey, Map<String, String> names)
    {
        String label = text(m, textKey), code = text(m, codeKey);
        return !label.isEmpty() ? label : names.getOrDefault(code, code.isEmpty() ? "未提供" : "未知状态("+code+")");
    }
    private static String text(Map<String, Object> m, String key) { return Objects.toString(m.get(key), "").trim(); }
    private static BigDecimal number(Map<String, Object> m, String key)
    { String n = text(m, key); return n.isEmpty() ? null : new BigDecimal(n); }
    private static LocalDateTime dateTime(String value)
    { return value.isEmpty() || value.startsWith("0000-") ? null : LocalDateTime.parse(value, TIME); }
    @SuppressWarnings("unchecked")
    private static List<Map<String, Object>> objects(Object value)
    {
        if (!(value instanceof List<?> list) || list.stream().anyMatch(v -> !(v instanceof Map)))
            throw new IllegalStateException("采购单接口明细格式异常");
        return (List<Map<String, Object>>) value;
    }
}
