package com.ruoyi.system.service.operation.external.lingxing;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.system.domain.operation.external.AmzProductListing;
import com.ruoyi.system.mapper.operation.external.AmzProductListingMapper;
import com.ruoyi.system.mapper.operation.external.ShopListMapper;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import java.util.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

/** 领星 Amazon Listing 同步 → amz_product_listing，按 sid 分页拉取（不清空，增量 upsert） */
@Service
public class LingxingAmzListingSyncService
{
    private static final Logger LOG = LoggerFactory.getLogger(LingxingAmzListingSyncService.class);
    private static final String API = "erp/sc/data/mws/listing";
    private final LingxingGatewayService gw;
    private final AmzProductListingMapper mapper;
    private final ShopListMapper shopMapper;
    private final ObjectMapper om;

    public LingxingAmzListingSyncService(LingxingGatewayService gw, AmzProductListingMapper mapper,
                                          ShopListMapper shopMapper, ObjectMapper om)
    { this.gw = gw; this.mapper = mapper; this.om = om; this.shopMapper = shopMapper; }

    public OperationSyncResult syncAll() throws Exception
    {
        long start = System.currentTimeMillis();
        List<String> sids = shopMapper.selectSidsByPlatform("10001", 1);
        if (sids.isEmpty()) sids = Collections.singletonList("0");
        int total = 0, pageSize = 1000;
        for (int i = 0; i < sids.size(); i += 20)
        {
            List<String> batch = sids.subList(i, Math.min(i + 20, sids.size()));
            int offset = 0;
            while (true)
            {
                Map<String, Object> body = new LinkedHashMap<>();
                body.put("sid", String.join(",", batch));
                body.put("is_pair", 1); body.put("is_delete", 0);
                body.put("offset", offset); body.put("length", pageSize);
                Map<String, Object> resp = gw.post(API, body);
                List<Map<String, Object>> list = getList(resp, "data");
                if (list.isEmpty()) break;
                for (Map<String, Object> row : list)
                {
                    Integer sid = intVal(row, "sid");
                    String sellerSku = str(row, "seller_sku", "sellerSku");
                    if (sid == null || !StringUtils.hasText(sellerSku)) continue;
                    Integer status = intVal(row, "status");
                    List<AmzProductListing> ex = mapper.selectBySidSellerSku(sid, sellerSku);
                    AmzProductListing e = ex.isEmpty() ? new AmzProductListing() : ex.get(0);
                    e.setSid(sid); e.setSellerSku(sellerSku);
                    e.setStatus(status != null ? status : 1);
                    e.setMarketplace(str(row, "marketplace"));
                    e.setAsin(str(row, "asin"));
                    e.setLocalSku(str(row, "local_sku", "localSku"));
                    e.setLocalName(str(row, "local_name", "localName"));
                    e.setReviewNum(intVal(row, "review_num", "reviewNum"));
                    e.setLastStar(str(row, "last_star", "lastStar"));
                    e.setPrincipalName(extractPrincipalName(row));
                    e.setTagName(extractTagName(row));
                    if (ex.isEmpty()) mapper.insert(e); else mapper.updateById(e);
                    total++;
                }
                if (list.size() < pageSize) break;
                offset += pageSize;
            }
            if (i + 20 < sids.size()) Thread.sleep(1000);
        }
        return OperationSyncResult.success("amz_listing", "领星-Amazon商品刊登", API, total, total, System.currentTimeMillis() - start);
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> getList(Map<String, Object> r, String k)
    { Object o = r.get(k); if (o instanceof List) return (List<Map<String, Object>>) o; try { return om.convertValue(o, new TypeReference<List<Map<String, Object>>>() {}); } catch (Exception e) { return new ArrayList<>(); } }
    @SuppressWarnings("unchecked")
    private String extractPrincipalName(Map<String, Object> row) {
        Object info = row.get("principal_info");
        if (info instanceof List) {
            List<Map<String, Object>> list = (List<Map<String, Object>>) info;
            if (!list.isEmpty()) {
                Object name = list.get(0).get("principal_name");
                return name != null ? String.valueOf(name) : null;
            }
        }
        return null;
    }

    @SuppressWarnings("unchecked")
    private String extractTagName(Map<String, Object> row) {
        Object tags = row.get("global_tags");
        if (tags instanceof List) {
            List<Map<String, Object>> list = (List<Map<String, Object>>) tags;
            StringBuilder sb = new StringBuilder();
            for (Map<String, Object> tag : list) {
                Object name = tag.get("tagName");
                if (name != null && !name.toString().isEmpty()) {
                    if (sb.length() > 0) sb.append(',');
                    sb.append(name.toString());
                }
            }
            return sb.toString();
        }
        return null;
    }
    private String str(Map<String, Object> m, String... ks) { for (String k : ks) { Object v = m.get(k); if (v != null && StringUtils.hasText(v.toString())) return v.toString(); } return null; }
    private Integer intVal(Map<String, Object> m, String... ks) { String s = str(m, ks); if (s == null) return null; try { return Integer.valueOf(s); } catch (Exception e) { return null; } }
}
