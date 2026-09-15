package com.ruoyi.system.service.operation.external.lingxing;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.system.domain.operation.external.AmzFbaShipment;
import com.ruoyi.system.mapper.operation.external.AmzFbaShipmentMapper;
import com.ruoyi.system.mapper.operation.external.ShopListMapper;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import java.text.SimpleDateFormat;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

/**
 * 领星 Amazon FBA 货件同步 → amz_fba_shipment。
 * API: /erp/sc/data/fba_report/shipmentList
 * 每行 item 展平为一个明细记录，按 (sid, shipment_id, sku) 唯一键 upsert。
 */
@Service
public class AmzFbaShipmentSyncService
{
    private static final Logger LOG = LoggerFactory.getLogger(AmzFbaShipmentSyncService.class);
    private static final String API = "erp/sc/data/fba_report/shipmentList";
    // API 返回 gmt_create/gmt_modified 格式为 yyyy-MM-dd HH:mm（无秒）
    private static final DateTimeFormatter[] DT_FORMATS = {
        DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss"),
        DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm")
    };

    private final LingxingGatewayService gw;
    private final AmzFbaShipmentMapper mapper;
    private final ShopListMapper shopMapper;
    private final ObjectMapper om;

    public AmzFbaShipmentSyncService(LingxingGatewayService gw, AmzFbaShipmentMapper mapper,
                                      ShopListMapper shopMapper, ObjectMapper om)
    { this.gw = gw; this.mapper = mapper; this.om = om; this.shopMapper = shopMapper; }

    /** 全量拉取最近365天 */
    public OperationSyncResult sync() throws Exception
    {
        LocalDate end = LocalDate.now();
        LocalDate start = end.minusDays(365);
        return sync(start, end);
    }

    /** 校准模式：指定日期范围全量拉取并 upsert */
    public OperationSyncResult sync(LocalDate startDate, LocalDate endDate) throws Exception
    {
        long start = System.currentTimeMillis();
        List<String> sids = shopMapper.selectSidsByPlatform("10001", 1);
        if (sids.isEmpty())
        {
            return OperationSyncResult.success("amz_fba_shipment", "领星-FBA货件", API, 0, 0, System.currentTimeMillis() - start);
        }

        // 在任何写入之前取时间戳：本次写入的行 sync_time = NOW() 必然大于它，
        // 清理时用它区分"本次刷新过的"和"接口已不再返回的"。
        // 取库时间而不是 new Date()：sync_time 写的是 MySQL 的 NOW()，
        // 若 Java 与 MySQL 不同主机且库时钟偏慢，本次写入的行会被误判为陈旧行。
        Date runStart = mapper.selectDatabaseNow();
        // 只记录本次确实返回过数据的店铺。某个店铺接口异常返回空时，
        // 它不会进这个集合，其历史数据一行都不会被清理。
        Set<Integer> syncedSids = new LinkedHashSet<>();

        int total = 0, pageSize = 200;
        // 每批20个sid
        for (int i = 0; i < sids.size(); i += 20)
        {
            List<String> batch = sids.subList(i, Math.min(i + 20, sids.size()));
            int offset = 0;
            while (true)
            {
                Map<String, Object> body = new LinkedHashMap<>();
                body.put("sid", String.join(",", batch));
                body.put("start_date", startDate.toString());
                body.put("end_date", endDate.toString());
                body.put("offset", offset);
                body.put("length", pageSize);
                Map<String, Object> resp = gw.post(API, body);
                List<Map<String, Object>> data = getDataList(resp);
                if (data.isEmpty()) break;

                List<AmzFbaShipment> rows = new ArrayList<>();
                for (Map<String, Object> shipment : data)
                {
                    Integer sid = intVal(shipment, "sid");
                    String username = str(shipment, "username");
                    if (sid == null) continue;
                    String shipmentId = str(shipment, "shipment_id");
                    String shipmentName = str(shipment, "shipment_name");
                    String shipmentStatus = str(shipment, "shipment_status");
                    Date gmtCreate = parseDt(str(shipment, "gmt_create"));
                    Date gmtModified = parseDt(str(shipment, "gmt_modified"));

                    // ship_to_address
                    String stName = null, stCountry = null, stState = null, stCity = null,
                           stRegion = null, stAddr1 = null, stAddr2 = null, stZip = null, stDoor = null;
                    @SuppressWarnings("unchecked")
                    Map<String, Object> shipTo = (Map<String, Object>) shipment.get("ship_to_address");
                    if (shipTo != null) {
                        stName = str(shipTo, "name");
                        stCountry = str(shipTo, "country_code");
                        stState = str(shipTo, "state_or_province_code");
                        stCity = str(shipTo, "city");
                        stRegion = str(shipTo, "region");
                        stAddr1 = str(shipTo, "address_line1");
                        stAddr2 = str(shipTo, "address_line2");
                        stZip = str(shipTo, "postal_code");
                        stDoor = str(shipTo, "doorplate");
                    }

                    @SuppressWarnings("unchecked")
                    List<Map<String, Object>> items = (List<Map<String, Object>>) shipment.get("item_list");
                    if (items == null || items.isEmpty()) continue;

                    for (Map<String, Object> item : items)
                    {
                        String msku = str(item, "msku");
                        String sku = str(item, "sku");
                        if (sku == null || sku.isEmpty()) sku = msku;
                        if (sku == null || sku.isEmpty()) continue;

                        AmzFbaShipment row = new AmzFbaShipment();
                        row.setSid(sid);
                        row.setUsername(username);
                        row.setShipmentId(shipmentId != null ? shipmentId : "");
                        row.setShipmentName(shipmentName != null ? shipmentName : "");
                        row.setShipmentStatus(shipmentStatus != null ? shipmentStatus : "");
                        row.setMsku(msku != null ? msku : "");
                        row.setSku(sku);
                        row.setQuantityShipped(intVal(item, "quantity_shipped"));
                        row.setInitQuantityShipped(intVal(item, "init_quantity_shipped"));
                        row.setQuantityReceived(intVal(item, "quantity_received"));
                        row.setQuantityShippedLocal(intVal(item, "quantity_shipped_local"));
                        row.setGmtCreate(gmtCreate);
                        row.setGmtModified(gmtModified);
                        row.setWorkingTime(parseDt(str(shipment, "working_time")));
                        row.setShippedTime(parseDt(str(shipment, "shipped_time")));
                        row.setReceivingTime(parseDt(str(shipment, "receiving_time")));
                        row.setClosedTime(parseDt(str(shipment, "closed_time")));
                        row.setStaDeliveryStartDate(parseDate(str(shipment, "sta_delivery_start_date")));
                        row.setShipToName(stName);
                        row.setShipToCountryCode(stCountry);
                        row.setShipToState(stState);
                        row.setShipToCity(stCity);
                        row.setShipToRegion(stRegion);
                        row.setShipToAddressLine1(stAddr1);
                        row.setShipToAddressLine2(stAddr2);
                        row.setShipToPostalCode(stZip);
                        row.setShipToDoorplate(stDoor);
                        rows.add(row);
                    }
                }
                if (!rows.isEmpty())
                {
                    mapper.batchUpsert(rows);
                    total += rows.size();
                    for (AmzFbaShipment r : rows) syncedSids.add(r.getSid());
                }

                int remoteTotal = getInt(resp, "total");
                if (remoteTotal > 0 && offset + pageSize >= remoteTotal) break;
                if (data.size() < pageSize) break;
                offset += pageSize;
            }
            if (i + 20 < sids.size()) Thread.sleep(1000);
        }

        // 走到这里说明所有店铺、所有分页都成功了：方法内没有 try/catch，
        // 中途任何异常都会直接冒泡，根本到不了清理这一步。
        int removed = cleanupStaleRows(syncedSids, runStart, startDate, endDate, total);

        OperationSyncResult result = OperationSyncResult.success(
                "amz_fba_shipment", "领星-FBA货件", API, total, total,
                System.currentTimeMillis() - start);
        result.setBusinessSummary("拉取" + total + "条；覆盖店铺" + syncedSids.size()
                + "个；清理接口已不返回的陈旧行" + removed + "条");
        return result;
    }

    /**
     * 清理接口已不再返回的陈旧行。
     *
     * <p>领星改本地SKU名时，msku 不变而 sku 变了。唯一键是 (sid, shipment_id, sku)，
     * 所以 upsert 会插入新行，旧行留在表里，同一条货件明细就存了两份，
     * 按货件汇总申报量会翻倍。此方法在每次完整同步后清掉旧的那份。
     *
     * <p>四道安全闸：
     * <ol>
     *   <li>只清 syncedSids —— 本次确实返回过数据的店铺。某店铺接口异常返回空时，
     *       它不在集合里，历史数据一行不动。</li>
     *   <li>只清 gmt_create 落在本次同步窗口内的 —— 窗口外的货件接口本来就不返回，
     *       不能当成陈旧行。</li>
     *   <li>只在方法跑到最后才调用 —— 中途抛异常走不到这里。</li>
     *   <li>sync_time 早于 runStart —— 本次写入的行 sync_time 更晚，不会误删。</li>
     * </ol>
     *
     * <p>另有熔断：待清理量超过本次拉取量的 5% 时只告警不删，
     * 防止接口大面积返回空 item_list 时造成灾难性误删。
     */
    private int cleanupStaleRows(Set<Integer> syncedSids, Date runStart,
                                 LocalDate startDate, LocalDate endDate, int total)
    {
        if (syncedSids.isEmpty()) return 0;
        int candidates = mapper.countStaleBySids(syncedSids, runStart, startDate, endDate);
        if (candidates == 0) return 0;
        if (total > 0 && candidates > total * 0.05)
        {
            LOG.error("FBA货件待清理陈旧行{}条，超过本次拉取{}条的5%，已跳过清理，请人工核查接口返回是否异常",
                    candidates, total);
            return 0;
        }
        int removed = mapper.deleteStaleBySids(syncedSids, runStart, startDate, endDate);
        LOG.info("FBA货件清理接口已不返回的陈旧行{}条，覆盖店铺{}个", removed, syncedSids.size());
        return removed;
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> getDataList(Map<String, Object> resp)
    {
        Object d = resp.get("data");
        if (d instanceof Map) {
            Object list = ((Map<String, Object>) d).get("list");
            if (list instanceof List) return (List<Map<String, Object>>) list;
            try { return om.convertValue(list, new TypeReference<List<Map<String, Object>>>() {}); }
            catch (Exception e) { return new ArrayList<>(); }
        }
        return new ArrayList<>();
    }

    private String str(Map<String, Object> m, String k) { Object v = m.get(k); return v != null ? String.valueOf(v) : null; }
    private int getInt(Map<String, Object> m, String k) { Object v = m.get(k); if (v instanceof Number) return ((Number) v).intValue(); return 0; }
    private Integer intVal(Map<String, Object> m, String k) { Object v = m.get(k); if (v instanceof Number) return ((Number) v).intValue(); if (v != null) try { return Integer.parseInt(v.toString()); } catch (Exception e) {} return 0; }
    private Date parseDt(String s) {
        if (!StringUtils.hasText(s)) return null;
        for (DateTimeFormatter fmt : DT_FORMATS) {
            try { return java.util.Date.from(LocalDateTime.parse(s, fmt).atZone(java.time.ZoneId.systemDefault()).toInstant()); }
            catch (Exception ignored) {}
        }
        return null;
    }

    /**
     * 解析纯日期字段（sta_delivery_start_date）。
     * 不能复用 parseDt：它走 LocalDateTime.parse，遇到 10 位纯日期会全部解析失败。
     * 接口文档标称 yyyy-MM-dd HH:mm:ss，实测返回的全部是 yyyy-MM-dd，
     * 这里两种都兼容：先按纯日期解析，失败再退回按日期时间解析后取日期部分。
     */
    private Date parseDate(String s) {
        if (!StringUtils.hasText(s)) return null;
        String text = s.trim();
        try { return java.sql.Date.valueOf(LocalDate.parse(text, DateTimeFormatter.ISO_LOCAL_DATE)); }
        catch (Exception ignored) {}
        for (DateTimeFormatter fmt : DT_FORMATS) {
            try { return java.sql.Date.valueOf(LocalDateTime.parse(text, fmt).toLocalDate()); }
            catch (Exception ignored) {}
        }
        return null;
    }
}
