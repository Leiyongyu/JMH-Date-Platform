package com.ruoyi.system.service.operation.external.lingxing;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.system.domain.operation.external.WarehouseInventoryDetail;
import com.ruoyi.system.mapper.operation.external.WarehouseInventoryDetailMapper;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import java.math.BigDecimal;
import java.util.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

/** 领星库存明细同步 → warehouse_inventory_detail，按 wid 分页拉取并批量覆盖写入 */
@Service
public class LingxingInventorySyncService
{
    private static final Logger LOG = LoggerFactory.getLogger(LingxingInventorySyncService.class);
    private static final String API = "erp/sc/routing/data/local_inventory/inventoryDetails";
    private final LingxingGatewayService gw;
    private final WarehouseInventoryDetailMapper mapper;
    private final ObjectMapper om;
    private final LingxingProperties props;

    public LingxingInventorySyncService(LingxingGatewayService gw, WarehouseInventoryDetailMapper mapper,
                                         ObjectMapper om, LingxingProperties props)
    { this.gw = gw; this.mapper = mapper; this.om = om; this.props = props; }

    public OperationSyncResult syncAll() throws Exception
    {
        long start = System.currentTimeMillis();
        mapper.deleteAll();
        String widsStr = props.getInventoryWids();
        if (!StringUtils.hasText(widsStr)) widsStr = "18676,18701,18675,18674,18702,18700,18699";
        String[] wids = widsStr.split(",");
        int total = 0;
        for (String wid : wids)
        {
            int offset = 0, length = 200;
            while (true)
            {
                Map<String, Object> body = new LinkedHashMap<>();
                body.put("wid", wid.trim());
                body.put("offset", offset);
                body.put("length", length);
                Map<String, Object> resp = gw.post(API, body);
                List<Map<String, Object>> list = getList(resp, "data");
                if (list == null || list.isEmpty()) break;
                List<WarehouseInventoryDetail> batch = new ArrayList<>();
                for (Map<String, Object> row : list)
                {
                    WarehouseInventoryDetail d = new WarehouseInventoryDetail();
                    d.setWid(wid.trim());
                    d.setSku(str(row, "sku"));
                    d.setProductId(str(row, "product_id", "productId"));
                    d.setSellerId(str(row, "seller_id", "sellerId"));
                    d.setFnsku(str(row, "fnsku"));
                    d.setProductValidNum(str(row, "product_valid_num", "productValidNum"));
                    d.setProductLockNum(str(row, "product_lock_num", "productLockNum"));
                    d.setProductOnway(str(row, "product_onway", "productOnway"));
                    d.setQuantityReceive(str(row, "quantity_receive", "quantityReceive"));
                    batch.add(d);
                }
                if (!batch.isEmpty()) { mapper.batchInsert(batch); total += batch.size(); }
                if (list.size() < length) break;
                offset += length;
            }
        }
        return OperationSyncResult.success("lingxing_inv", "领星-库存明细", API, total, total, System.currentTimeMillis() - start);
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> getList(Map<String, Object> r, String k)
    {
        Object o = r.get(k);
        if (o instanceof List) return (List<Map<String, Object>>) o;
        try { return om.convertValue(o, new TypeReference<List<Map<String, Object>>>() {}); } catch (Exception e) { return new ArrayList<>(); }
    }
    private String str(Map<String, Object> m, String... ks)
    { for (String k : ks) { Object v = m.get(k); if (v != null && StringUtils.hasText(v.toString())) return v.toString(); } return null; }
    private int intVal(Map<String, Object> m, String... ks)
    { String s = str(m, ks); return s != null ? Integer.parseInt(s) : 0; }
    private BigDecimal bdVal(Map<String, Object> m, String... ks)
    { String s = str(m, ks); return s != null ? new BigDecimal(s) : null; }
}
