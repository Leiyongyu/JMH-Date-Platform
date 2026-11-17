package com.ruoyi.system.service.operation.external.lingxing;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.system.domain.operation.external.AmzWarehouseInventoryDetail;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

/**
 * 领星 Amazon 仓库库存明细同步。
 *
 * <p>接口可能按店铺关联返回相同仓库、相同 SKU 的多条记录；这些记录共享同一份物理库存，
 * 因此各库存字段取最大值而不是求和。所有仓库和分页完整拉取、合并、校验后，才原子替换数据库。
 */
@Service
public class AmzWarehouseInventorySyncService
{
    private static final Logger LOG = LoggerFactory.getLogger(AmzWarehouseInventorySyncService.class);
    private static final String API = "erp/sc/routing/data/local_inventory/inventoryDetails";
    private static final String[] AMZ_WIDS = {"18677", "19561", "18678", "18679", "18680"};
    private static final int PAGE_SIZE = 800;
    private static final int DUPLICATE_LOG_LIMIT = 20;

    private final LingxingGatewayService gw;
    private final ObjectMapper om;
    private final AmzWarehouseInventoryReplaceService replaceService;

    public AmzWarehouseInventorySyncService(
            LingxingGatewayService gw,
            ObjectMapper om,
            AmzWarehouseInventoryReplaceService replaceService)
    {
        this.gw = gw;
        this.om = om;
        this.replaceService = replaceService;
    }

    public OperationSyncResult syncAll() throws Exception
    {
        long start = System.currentTimeMillis();
        Map<String, AmzWarehouseInventoryDetail> mergedRows = new LinkedHashMap<>();
        int sourceRows = 0;
        int duplicateRows = 0;

        for (String wid : AMZ_WIDS)
        {
            int offset = 0;
            while (true)
            {
                Map<String, Object> body = new LinkedHashMap<>();
                body.put("wid", wid);
                body.put("offset", offset);
                body.put("length", PAGE_SIZE);

                Map<String, Object> resp = gw.post(API, body);
                List<Map<String, Object>> list = getList(resp, "data");
                if (list.isEmpty()) break;
                int remoteTotal = getInt(resp, "total");

                for (Map<String, Object> row : list)
                {
                    sourceRows++;
                    AmzWarehouseInventoryDetail incoming = toEntity(wid, row);
                    if (incoming == null) continue;

                    String key = inventoryKey(incoming.getWid(), incoming.getSku());
                    AmzWarehouseInventoryDetail current = mergedRows.putIfAbsent(key, incoming);
                    if (current != null)
                    {
                        duplicateRows++;
                        Integer previousValidNum = current.getProductValidNum();
                        mergeInventory(current, incoming);
                        if (duplicateRows <= DUPLICATE_LOG_LIMIT)
                        {
                            LOG.warn(
                                    "Amazon仓库库存重复：wid={}, sku={}, 原可用量={}, 新可用量={}, 合并后={}",
                                    current.getWid(), current.getSku(), previousValidNum,
                                    incoming.getProductValidNum(), current.getProductValidNum());
                        }
                    }
                }

                if (remoteTotal > 0 && offset + PAGE_SIZE >= remoteTotal) break;
                if (list.size() < PAGE_SIZE) break;
                offset += PAGE_SIZE;
            }
        }

        List<AmzWarehouseInventoryDetail> allRows = new ArrayList<>(mergedRows.values());
        validateInventory(allRows);
        int inserted = replaceService.replaceAll(allRows);

        if (duplicateRows > DUPLICATE_LOG_LIMIT)
        {
            LOG.warn("Amazon仓库库存另有{}条重复记录未逐条打印，详见同步汇总",
                    duplicateRows - DUPLICATE_LOG_LIMIT);
        }
        LOG.info("Amazon仓库库存同步完成：接口原始记录={}，合并后记录={}，重复记录={}，写入记录={}",
                sourceRows, mergedRows.size(), duplicateRows, inserted);

        return OperationSyncResult.success(
                "amz_wh_inv",
                "领星-Amazon库存明细",
                API,
                inserted,
                inserted,
                System.currentTimeMillis() - start);
    }

    private AmzWarehouseInventoryDetail toEntity(String wid, Map<String, Object> row)
    {
        String sku = str(row, "sku");
        if (!StringUtils.hasText(sku)) return null;

        AmzWarehouseInventoryDetail entity = new AmzWarehouseInventoryDetail();
        entity.setWid(Integer.parseInt(wid));
        entity.setSellerId(normalizeNullable(str(row, "seller_id", "sellerId")));
        entity.setSku(sku.strip());
        entity.setQuantityReceive(bd(row, "quantity_receive", "quantityReceive"));
        entity.setProductValidNum(intVal(row, "product_valid_num", "productValidNum"));
        entity.setProductLockNum(intVal(row, "product_lock_num", "productLockNum"));
        entity.setProductQcNum(intVal(row, "product_qc_num", "productQcNum"));
        return entity;
    }

    private void validateInventory(List<AmzWarehouseInventoryDetail> rows)
    {
        if (rows == null || rows.isEmpty())
        {
            throw new IllegalStateException("领星-Amazon库存明细返回0条有效数据，已保留原库存数据");
        }
    }

    static String inventoryKey(Integer wid, String sku)
    {
        return String.valueOf(wid) + "|" + normalizeSku(sku).toLowerCase(Locale.ROOT);
    }

    static void mergeInventory(
            AmzWarehouseInventoryDetail current,
            AmzWarehouseInventoryDetail incoming)
    {
        current.setProductValidNum(max(current.getProductValidNum(), incoming.getProductValidNum()));
        current.setProductLockNum(max(current.getProductLockNum(), incoming.getProductLockNum()));
        current.setProductQcNum(max(current.getProductQcNum(), incoming.getProductQcNum()));
        current.setQuantityReceive(max(current.getQuantityReceive(), incoming.getQuantityReceive()));

        if (!StringUtils.hasText(current.getSellerId())
                && StringUtils.hasText(incoming.getSellerId()))
        {
            current.setSellerId(incoming.getSellerId().strip());
        }
    }

    private static Integer max(Integer left, Integer right)
    {
        return Math.max(left == null ? 0 : left, right == null ? 0 : right);
    }

    private static BigDecimal max(BigDecimal left, BigDecimal right)
    {
        BigDecimal a = left == null ? BigDecimal.ZERO : left;
        BigDecimal b = right == null ? BigDecimal.ZERO : right;
        return a.max(b);
    }

    private static String normalizeSku(String value)
    {
        return value == null ? "" : value.strip();
    }

    private static String normalizeNullable(String value)
    {
        return StringUtils.hasText(value) ? value.strip() : null;
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> getList(Map<String, Object> response, String key)
    {
        if (response == null) return new ArrayList<>();
        Object value = response.get(key);
        if (value == null) return new ArrayList<>();
        if (value instanceof List) return (List<Map<String, Object>>) value;
        try
        {
            List<Map<String, Object>> result =
                    om.convertValue(value, new TypeReference<List<Map<String, Object>>>() {});
            return result != null ? result : new ArrayList<>();
        }
        catch (Exception ex)
        {
            throw new IllegalStateException("领星-Amazon库存明细响应格式异常", ex);
        }
    }

    private int getInt(Map<String, Object> map, String key)
    {
        Object value = map != null ? map.get(key) : null;
        if (value instanceof Number) return ((Number) value).intValue();
        if (value != null)
        {
            try
            {
                return new BigDecimal(value.toString()).intValue();
            }
            catch (Exception ignored)
            {
            }
        }
        return 0;
    }

    private String str(Map<String, Object> map, String... keys)
    {
        for (String key : keys)
        {
            Object value = map.get(key);
            if (value != null && StringUtils.hasText(value.toString()))
            {
                return value.toString();
            }
        }
        return null;
    }

    private Integer intVal(Map<String, Object> map, String... keys)
    {
        String value = str(map, keys);
        return value != null ? new BigDecimal(value).intValue() : null;
    }

    private BigDecimal bd(Map<String, Object> map, String... keys)
    {
        String value = str(map, keys);
        return value != null ? new BigDecimal(value) : null;
    }
}
