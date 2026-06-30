package com.ruoyi.system.service.operation.external.lingxing;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.system.domain.operation.external.LingxingProductWeight;
import com.ruoyi.system.mapper.operation.external.LingxingProductWeightMapper;
import com.ruoyi.system.mapper.operation.external.OverseasStockOrderDetailMapper;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import java.math.BigDecimal;
import java.util.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

/** 领星产品毛重同步 → lingxing_product_weight */
@Service
public class LingxingProductWeightSyncService
{
    private static final Logger LOG = LoggerFactory.getLogger(LingxingProductWeightSyncService.class);
    private static final String API = "erp/sc/routing/data/local_inventory/productInfo";

    private final LingxingGatewayService gw;
    private final LingxingProductWeightMapper mapper;
    private final OverseasStockOrderDetailMapper detailMapper;
    private final ObjectMapper om;

    public LingxingProductWeightSyncService(LingxingGatewayService gw, LingxingProductWeightMapper mapper,
                                             OverseasStockOrderDetailMapper detailMapper, ObjectMapper om)
    { this.gw = gw; this.mapper = mapper; this.detailMapper = detailMapper; this.om = om; }

    public OperationSyncResult sync() throws Exception
    {
        long start = System.currentTimeMillis();
        // 获取所有 SKU（完整格式）
        List<String> skus = detailMapper.selectDistinctSku();
        LOG.info("产品管理同步 共 {} 个SKU", skus.size());

        int total = 0;
        for (String sku : skus)
        {
            try
            {
                Map<String, Object> body = new LinkedHashMap<>();
                body.put("sku", sku);
                Map<String, Object> resp = gw.post(API, body);
                Map<String, Object> dd = getMap(resp, "data");
                if (dd == null || (dd.get("cg_product_gross_weight") == null && dd.get("cg_product_net_weight") == null)) {
                    if (total < 3) LOG.warn("产品管理 SKU={} 无数据, respKeys={}", sku, resp.keySet());
                    continue;
                }

                Object weightObj = dd.get("cg_product_gross_weight");
                Object netWeightObj = dd.get("cg_product_net_weight");

                LingxingProductWeight w = new LingxingProductWeight();
                w.setSku(sku);
                w.setGrossWeight(decimal(weightObj));
                w.setNetWeight(decimal(netWeightObj));
                mapper.upsert(w);
                total++;
            }
            catch (Exception e) { LOG.warn("产品毛重失败 {}: {}", sku, e.getMessage()); }
        }
        LOG.info("产品毛重同步完成: {} 条", total);
        return OperationSyncResult.success("product_weight", "领星-产品毛重", API, total, total, System.currentTimeMillis() - start);
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> getMap(Map<String, Object> r, String k)
    { Object o = r.get(k); return o instanceof Map ? (Map<String, Object>) o : null; }

    private BigDecimal decimal(Object value)
    {
        if (value == null) return null;
        String text = value.toString().trim();
        if (text.isEmpty()) return null;
        return new BigDecimal(text);
    }
}
