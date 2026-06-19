package com.ruoyi.system.service.operation.external.goodcang;

import com.ruoyi.system.domain.operation.external.GoodcangProductInfo;
import com.ruoyi.system.mapper.operation.external.GoodcangProductInfoMapper;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import java.math.BigDecimal;
import java.util.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

/** 谷仓商品信息同步 → goodcang_product_info，分页拉取全量覆盖 */
@Service
public class GoodcangProductSyncService
{
    private static final Logger LOG = LoggerFactory.getLogger(GoodcangProductSyncService.class);
    private final GoodcangClient client;
    private final GoodcangProductInfoMapper mapper;

    public GoodcangProductSyncService(GoodcangClient client, GoodcangProductInfoMapper mapper)
    { this.client = client; this.mapper = mapper; }

    public OperationSyncResult syncFromApi() throws Exception
    {
        long start = System.currentTimeMillis();
        mapper.deleteAll();
        int total = 0, page = 1, pageSize = 200;
        while (true)
        {
            Map<String, Object> resp = client.getProductList(page, pageSize);
            @SuppressWarnings("unchecked")
            List<Map<String, Object>> data = (List<Map<String, Object>>) resp.get("data");
            if (data == null || data.isEmpty()) break;
            for (Map<String, Object> row : data)
            {
                GoodcangProductInfo e = new GoodcangProductInfo();
                e.setSkuMiddle(str(row, "sku_middle"));
                e.setProductNameCn(str(row, "product_name_cn"));
                e.setRealWeight(bd(row, "real_weight"));
                e.setRealLength(bd(row, "real_length"));
                e.setRealWidth(bd(row, "real_width"));
                e.setRealHeight(bd(row, "real_height"));
                e.setVolume(bd(row, "volume"));
                e.setPrice(bd(row, "price"));
                mapper.insert(e);
                total++;
            }
            Object count = resp.get("count");
            int remoteTotal = count instanceof Number ? ((Number) count).intValue() : 0;
            if (remoteTotal > 0 && page * pageSize >= remoteTotal) break;
            if (data.size() < pageSize) break;
            page++;
        }
        return OperationSyncResult.success("gc_product", "谷仓-商品信息", "/product/get_product_sku_list", total, total, System.currentTimeMillis() - start);
    }
    private String str(Map<String, Object> m, String k) { Object v = m.get(k); return v != null ? v.toString() : null; }
    private BigDecimal bd(Map<String, Object> m, String k) { String s = str(m, k); return s != null ? new BigDecimal(s) : null; }
}
