package com.ruoyi.system.service.operation.external.lingxing;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.system.domain.operation.external.PurchasePlan;
import com.ruoyi.system.mapper.operation.external.PurchasePlanMapper;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

/** 领星采购计划同步 → purchase_plan，按 (plan_sn, sku) upsert */
@Service
public class LingxingPurchasePlanSyncService
{
    private static final Logger LOG = LoggerFactory.getLogger(LingxingPurchasePlanSyncService.class);
    private static final String API = "erp/sc/routing/data/local_inventory/getPurchasePlans";
    private static final DateTimeFormatter DT = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");

    private final LingxingGatewayService gw;
    private final PurchasePlanMapper mapper;
    private final ObjectMapper om;

    public LingxingPurchasePlanSyncService(LingxingGatewayService gw, PurchasePlanMapper mapper, ObjectMapper om)
    { this.gw = gw; this.mapper = mapper; this.om = om; }

    public OperationSyncResult sync() throws Exception
    {
        long start = System.currentTimeMillis();
        Map<String, PurchasePlan> existing = new HashMap<>();
        for (PurchasePlan e : mapper.selectAll())
            existing.put(e.getPlanSn() + "|" + e.getSku(), e);

        int inserted = 0, updated = 0, offset = 0, length = 500;
        String dateFrom = LocalDate.now().minusDays(1).toString();
        String dateTo = LocalDate.now().minusDays(1).toString();

        while (true)
        {
            Map<String, Object> body = new LinkedHashMap<>();
            body.put("search_field_time", "creator_time");
            body.put("start_date", dateFrom); body.put("end_date", dateTo);
            body.put("offset", offset); body.put("length", length);
            Map<String, Object> resp = gw.post(API, body);
            List<Map<String, Object>> list = getList(resp, "data");
            if (list.isEmpty()) break;
            int total = getInt(resp, "total");

            for (Map<String, Object> row : list)
            {
                String planSn = str(row, "plan_sn");
                String sku = str(row, "sku");
                if (planSn == null || planSn.isEmpty() || sku == null || sku.isEmpty()) continue;
                String key = planSn + "|" + sku;
                PurchasePlan e = existing.get(key);
                boolean isNew = (e == null);
                if (isNew) { e = new PurchasePlan(); e.setPlanSn(planSn); e.setSku(sku); }

                e.setPpgSn(str(row, "ppg_sn"));
                e.setProductName(str(row, "product_name"));
                e.setFnsku(str(row, "fnsku"));
                e.setPicUrl(str(row, "pic_url"));
                e.setSupplierId(str(row, "supplier_id"));
                e.setSupplierName(str(row, "supplier_name"));
                e.setStatusText(str(row, "status_text"));
                e.setStatus(intVal(row, "status"));
                e.setSid(str(row, "sid"));
                e.setSellerName(str(row, "seller_name"));
                e.setMarketplace(str(row, "marketplace"));
                e.setExpectArriveTime(str(row, "expect_arrive_time"));
                e.setRemark(str(row, "remark"));
                e.setQuantityPlan(intVal(row, "quantity_plan"));
                e.setProductId(intVal(row, "product_id"));
                e.setCgUid(intVal(row, "cg_uid"));
                e.setCgOptUsername(str(row, "cg_opt_username"));
                e.setCgBoxPcs(intVal(row, "cg_box_pcs"));
                e.setIsCombo(intVal(row, "is_combo"));
                e.setIsAux(intVal(row, "is_aux"));
                e.setIsRelatedProcessPlan(intVal(row, "is_related_process_plan"));
                e.setSpu(str(row, "spu"));
                e.setSpuName(str(row, "spu_name"));
                e.setCreatorUid(intVal(row, "creator_uid"));
                e.setCreatorRealName(str(row, "creator_real_name"));
                e.setWid(intVal(row, "wid"));
                e.setWarehouseName(str(row, "warehouse_name"));
                e.setPurchaserId(intVal(row, "purchaser_id"));
                e.setPurchaserName(str(row, "purchaser_name"));
                e.setCreateTime(parseDt(str(row, "create_time")));
                e.setPlanRemark(str(row, "plan_remark"));
                e.setAttributeJson(toJson(row.get("attribute")));
                e.setFileJson(toJson(row.get("file")));
                e.setMskuJson(toJson(row.get("msku")));
                e.setPermUidJson(toJson(row.get("perm_uid")));
                e.setPermUsernameJson(toJson(row.get("perm_username")));

                if (isNew) { mapper.insert(e); existing.put(key, e); inserted++; }
                else { mapper.updateById(e); updated++; }
            }
            offset += length;
            if (total <= 0 || offset >= total) break;
        }
        return OperationSyncResult.success("purchase_plan", "领星-采购计划", API, inserted+updated, inserted+updated, System.currentTimeMillis()-start);
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> getList(Map<String, Object> r, String k)
    { Object o = r.get(k); if (o instanceof List) return (List<Map<String, Object>>) o; try { return om.convertValue(o, new TypeReference<List<Map<String, Object>>>() {}); } catch (Exception e) { return new ArrayList<>(); } }
    private String str(Map<String, Object> m, String k) { Object v = m.get(k); return v != null ? v.toString() : null; }
    private int getInt(Map<String, Object> m, String k) { Object v = m.get(k); if (v instanceof Number) return ((Number)v).intValue(); return 0; }
    private Integer intVal(Map<String, Object> m, String k) { String s = str(m, k); return s != null ? Integer.valueOf(s) : null; }
    private Date parseDt(String s) {
        if (!StringUtils.hasText(s)) return null;
        try { return java.util.Date.from(LocalDateTime.parse(s, DT).atZone(java.time.ZoneId.systemDefault()).toInstant()); }
        catch (Exception e) { return null; }
    }
    private String toJson(Object v) { try { return v != null ? om.writeValueAsString(v) : null; } catch (Exception e) { return null; } }
}
