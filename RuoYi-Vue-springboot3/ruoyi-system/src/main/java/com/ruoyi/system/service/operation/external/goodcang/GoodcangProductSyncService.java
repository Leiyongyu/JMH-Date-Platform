package com.ruoyi.system.service.operation.external.goodcang;

import com.ruoyi.system.domain.operation.external.GoodcangProductInfo;
import com.ruoyi.system.mapper.operation.external.GoodcangProductInfoMapper;
import com.ruoyi.system.service.operation.compute.InventoryUtils;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.LocalDateTime;
import java.util.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

/** 谷仓商品同步 → goodcang_product_info。从 product_sku 提取中间码，去重后增量 upsert。 */
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

        // 1. 全量拉取
        List<Map<String, Object>> allRows = new ArrayList<>();
        int page = 1;
        while (true)
        {
            Map<String, Object> resp = client.getProductList(page, 100);
            @SuppressWarnings("unchecked")
            List<Map<String, Object>> data = (List<Map<String, Object>>) resp.getOrDefault("data", Collections.emptyList());
            if (data.isEmpty()) break;
            allRows.addAll(data);
            if (data.size() < 100) break;
            page++;
        }

        // 2. 按中间码去重
        Map<String, Map<String, Object>> deduped = new LinkedHashMap<>();
        int skipped = 0;
        for (Map<String, Object> row : allRows)
        {
            String sku = str(row, "product_sku");
            if (sku.isEmpty()) { skipped++; continue; }
            String mid = InventoryUtils.extractMiddleCodeForInventory(sku);
            if (mid.isEmpty()) { skipped++; continue; }
            deduped.putIfAbsent(mid, row);
        }

        // 3. 查已有记录
        Map<String, GoodcangProductInfo> existing = new LinkedHashMap<>();
        for (GoodcangProductInfo e : mapper.selectAll())
            if (StringUtils.hasText(e.getSkuMiddle())) existing.put(e.getSkuMiddle(), e);

        // 4. upsert
        int inserted = 0, updated = 0;
        for (Map.Entry<String, Map<String, Object>> e : deduped.entrySet())
        {
            String mid = e.getKey(); Map<String, Object> row = e.getValue();
            GoodcangProductInfo ent = existing.get(mid);
            boolean isNew = (ent == null);
            if (isNew) ent = new GoodcangProductInfo();
            ent.setSkuMiddle(mid);
            ent.setProductNameCn(str(row, "product_title_cn"));
            ent.setRealWeight(bd(row, "product_weight"));
            ent.setRealLength(bd(row, "product_length"));
            ent.setRealWidth(bd(row, "product_width"));
            ent.setRealHeight(bd(row, "product_height"));
            BigDecimal vLen = bd(row, "product_length"), vWid = bd(row, "product_width"), vHei = bd(row, "product_height");
            if (vLen != null && vWid != null && vHei != null && vLen.compareTo(BigDecimal.ZERO) > 0)
                ent.setVolume(vLen.multiply(vWid).multiply(vHei).divide(BigDecimal.valueOf(6000), 2, RoundingMode.HALF_UP));
            if (isNew) { mapper.insert(ent); inserted++; }
            else { mapper.updateById(ent); updated++; }
        }

        long elapsed = System.currentTimeMillis() - start;
        LOG.info("谷仓商品同步: {}条, 新增{}更新{}跳过{}", deduped.size(), inserted, updated, skipped);
        return OperationSyncResult.success("gc_product", "谷仓-商品信息", "/product/get_product_sku_list", inserted+updated, inserted+updated, elapsed);
    }

    private String str(Map<String, Object> m, String k) { Object v = m.get(k); return v != null ? String.valueOf(v) : ""; }
    private BigDecimal bd(Map<String, Object> m, String k) {
        Object v = m.get(k);
        if (v instanceof Number) return BigDecimal.valueOf(((Number) v).doubleValue());
        if (v != null) try { return new BigDecimal(String.valueOf(v)); } catch (Exception e) {}
        return null;
    }
}
