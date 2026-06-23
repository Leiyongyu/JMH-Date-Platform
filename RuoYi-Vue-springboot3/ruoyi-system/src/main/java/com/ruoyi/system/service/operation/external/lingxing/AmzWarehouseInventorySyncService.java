package com.ruoyi.system.service.operation.external.lingxing;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.system.domain.operation.external.AmzWarehouseInventoryDetail;
import com.ruoyi.system.mapper.operation.external.AmzWarehouseInventoryDetailMapper;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import java.math.BigDecimal;
import java.util.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

/** 领星 Amazon 仓库库存明细同步 → amz_warehouse_inventory_detail，对每个 wid 分页拉取，length=800，去重 */
@Service
public class AmzWarehouseInventorySyncService
{
    private static final Logger LOG = LoggerFactory.getLogger(AmzWarehouseInventorySyncService.class);
    private static final String API = "erp/sc/routing/data/local_inventory/inventoryDetails";
    private static final String[] AMZ_WIDS = {"18677","19561","18678","18679","18680"};
    private final LingxingGatewayService gw;
    private final AmzWarehouseInventoryDetailMapper mapper;
    private final ObjectMapper om;

    public AmzWarehouseInventorySyncService(LingxingGatewayService gw, AmzWarehouseInventoryDetailMapper mapper, ObjectMapper om)
    { this.gw = gw; this.mapper = mapper; this.om = om; }

    public OperationSyncResult syncAll() throws Exception
    {
        long start = System.currentTimeMillis();
        mapper.deleteAll();
        Set<String> seen = new HashSet<>();
        int total = 0;

        for (String wid : AMZ_WIDS)
        {
            int offset = 0, length = 800;
            while (true)
            {
                Map<String, Object> body = new LinkedHashMap<>();
                body.put("wid", wid); body.put("offset", offset); body.put("length", length);
                Map<String, Object> resp = gw.post(API, body);
                List<Map<String, Object>> list = getList(resp, "data");
                if (list.isEmpty()) break;
                int remoteTotal = getInt(resp, "total");

                List<AmzWarehouseInventoryDetail> batch = new ArrayList<>();
                for (Map<String, Object> row : list)
                {
                    String sku = str(row, "sku");
                    String sellerId = str(row, "seller_id", "sellerId");
                    String key = wid + "|" + sku;
                    if (!seen.add(key)) continue;
                    AmzWarehouseInventoryDetail e = new AmzWarehouseInventoryDetail();
                    e.setWid(Integer.parseInt(wid));
                e.setSellerId(sellerId);
                e.setSku(sku);
                e.setQuantityReceive(bd(row, "quantity_receive", "quantityReceive"));
                e.setProductValidNum(intVal(row, "product_valid_num", "productValidNum"));
                e.setProductLockNum(intVal(row, "product_lock_num", "productLockNum"));
                e.setProductQcNum(intVal(row, "product_qc_num", "productQcNum"));
                batch.add(e);
            }
                if (!batch.isEmpty()) { mapper.batchInsert(batch); total += batch.size(); }
                if (remoteTotal > 0 && offset + length >= remoteTotal) break;
                if (list.size() < length) break;
                offset += length;
            }
        }
        return OperationSyncResult.success("amz_wh_inv", "领星-Amazon库存明细", API, total, total, System.currentTimeMillis() - start);
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> getList(Map<String, Object> r, String k)
    { Object o = r.get(k); if (o instanceof List) return (List<Map<String, Object>>) o; try { return om.convertValue(o, new TypeReference<List<Map<String, Object>>>() {}); } catch (Exception e) { return new ArrayList<>(); } }
    private int getInt(Map<String, Object> m, String k) { Object v = m.get(k); if (v instanceof Number) return ((Number)v).intValue(); if (v != null) try { return Integer.parseInt(v.toString()); } catch (Exception e) {} return 0; }
    private String str(Map<String, Object> m, String... ks) { for (String k : ks) { Object v = m.get(k); if (v != null && StringUtils.hasText(v.toString())) return v.toString(); } return null; }
    private Integer intVal(Map<String, Object> m, String... ks) { String s = str(m, ks); return s != null ? Integer.valueOf(s) : null; }
    private BigDecimal bd(Map<String, Object> m, String... ks) { String s = str(m, ks); return s != null ? new BigDecimal(s) : null; }
}
