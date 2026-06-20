package com.ruoyi.system.service.operation.external.goodcang;

import com.ruoyi.system.domain.operation.external.GoodcangWarehouse;
import com.ruoyi.system.mapper.operation.external.GoodcangWarehouseMapper;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import java.util.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

/** 谷仓仓库同步 → goodcang_warehouse，清空后全量写入 */
@Service
public class GoodcangWarehouseSyncService
{
    private static final Logger LOG = LoggerFactory.getLogger(GoodcangWarehouseSyncService.class);
    private final GoodcangClient client;
    private final GoodcangWarehouseMapper mapper;

    public GoodcangWarehouseSyncService(GoodcangClient client, GoodcangWarehouseMapper mapper)
    { this.client = client; this.mapper = mapper; }

    public OperationSyncResult syncWarehouses() throws Exception
    {
        long start = System.currentTimeMillis();
        Map<String, Object> resp = client.getWarehouses();
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> data = (List<Map<String, Object>>) resp.get("data");
        if (data == null) return OperationSyncResult.success("gc_wh", "谷仓-仓库信息", "/base_data/get_warehouse", 0, 0, System.currentTimeMillis() - start);

        mapper.deleteAll();
        List<GoodcangWarehouse> list = new ArrayList<>();
        for (Map<String, Object> wh : data)
        {
            String wcode = str(wh, "warehouse_code"), wname = str(wh, "warehouse_name"), cc = str(wh, "country_code");
            @SuppressWarnings("unchecked")
            List<Map<String, Object>> wpList = (List<Map<String, Object>>) wh.get("wp_list");
            if (wpList == null) continue;
            for (Map<String, Object> wp : wpList)
            {
                GoodcangWarehouse e = new GoodcangWarehouse();
                e.setWarehouseCode(wcode); e.setWarehouseName(wname); e.setCountryCode(cc);
                e.setWpCode(str(wp, "code")); e.setWpName(str(wp, "name"));
                list.add(e);
            }
        }
        if (!list.isEmpty()) mapper.batchInsert(list);
        int matched = mapper.fillWidByFuzzyMatch();
        LOG.info("谷仓仓库同步: {}条, wid模糊匹配{}条", list.size(), matched);
        return OperationSyncResult.success("gc_wh", "谷仓-仓库信息", "/base_data/get_warehouse", list.size(), list.size(), System.currentTimeMillis() - start);
    }
    private String str(Map<String, Object> m, String k) { Object v = m.get(k); return v != null ? v.toString() : null; }
}
