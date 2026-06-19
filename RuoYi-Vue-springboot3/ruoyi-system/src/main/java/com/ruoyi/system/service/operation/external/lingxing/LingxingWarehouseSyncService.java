package com.ruoyi.system.service.operation.external.lingxing;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.system.domain.operation.external.Warehouse;
import com.ruoyi.system.mapper.operation.external.WarehouseMapper;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;

/**
 * 领星仓库同步服务 —— 从领星拉取仓库数据，增量 upsert 到 warehouse 表。
 * 从旧项目 LingxingWarehouseService 迁移，适配新项目 MyBatis 架构。
 *
 * @author JMH
 */
@Service
public class LingxingWarehouseSyncService
{
    private static final Logger LOG = LoggerFactory.getLogger(LingxingWarehouseSyncService.class);
    private static final String API_PATH = "erp/sc/data/local_inventory/warehouse";

    private final LingxingGatewayService gateway;
    private final WarehouseMapper warehouseMapper;
    private final ObjectMapper objectMapper;

    public LingxingWarehouseSyncService(LingxingGatewayService gateway,
                                         WarehouseMapper warehouseMapper,
                                         ObjectMapper objectMapper)
    {
        this.gateway = gateway;
        this.warehouseMapper = warehouseMapper;
        this.objectMapper = objectMapper;
    }

    /**
     * 同步所有类型仓库（本地仓1、海外仓3、亚马逊平台仓4、AWD仓6），合并写入。
     */
    @Transactional
    public OperationSyncResult syncWarehouses() throws Exception
    {
        long start = System.currentTimeMillis();
        int[] types = {1, 3, 4, 6};
        int totalInserted = 0, totalUpdated = 0, totalRemote = 0;
        List<OperationSyncResult.FailureItem> failures = new ArrayList<>();

        for (int type : types)
        {
            try
            {
                Map<String, Object> resp = fetchWarehouses(type);
                List<Map<String, Object>> data = getDataList(resp);
                if (data.isEmpty())
                {
                    continue;
                }
                totalRemote += data.size();

                int[] stats = upsertWarehouses(data);
                totalInserted += stats[0];
                totalUpdated += stats[1];
            }
            catch (Exception e)
            {
                LOG.error("同步仓库 type={} 失败: {}", type, e.getMessage());
                failures.add(new OperationSyncResult.FailureItem(
                        "type=" + type, e.getMessage()));
            }
        }

        long elapsed = System.currentTimeMillis() - start;
        int totalSuccess = totalInserted + totalUpdated;

        if (!failures.isEmpty() && totalSuccess == 0)
        {
            return OperationSyncResult.failed("warehouse", "领星-仓库信息", API_PATH,
                    "所有类型同步失败", elapsed);
        }

        if (!failures.isEmpty())
        {
            return OperationSyncResult.partial("warehouse", "领星-仓库信息", API_PATH,
                    totalRemote, totalSuccess, failures.size(), failures, elapsed);
        }

        return OperationSyncResult.success("warehouse", "领星-仓库信息", API_PATH,
                totalRemote, totalSuccess, elapsed);
    }

    // ========== 内部方法 ==========

    /** 调用领星 API 获取指定类型的仓库列表（单页，最多1000条） */
    private Map<String, Object> fetchWarehouses(int type) throws Exception
    {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("type", type);
        body.put("is_delete", 0);
        body.put("offset", 0);
        body.put("length", 1000);

        Map<String, Object> resp = gateway.post(API_PATH, body);
        LOG.info("领星仓库 type={} API 响应 code={}, msg={}, data是否为null={}",
                type, resp.get("code"), resp.get("msg"),
                resp.get("data") == null);
        return resp;
    }

    /** 批量 upsert 仓库数据，返回 [inserted, updated] */
    private int[] upsertWarehouses(List<Map<String, Object>> rows)
    {
        // 1. 收集所有 wid
        List<Integer> wids = new ArrayList<>();
        for (Map<String, Object> row : rows)
        {
            Integer wid = getInt(row, "wid", "warehouse_id", "id");
            if (wid != null) wids.add(wid);
        }
        if (wids.isEmpty()) return new int[]{0, 0};

        // 2. 批量查询已存在的仓库
        Map<Integer, Warehouse> existing = new HashMap<>();
        for (Warehouse w : warehouseMapper.selectByWids(wids))
        {
            if (w.getWid() != null)
            {
                existing.put(w.getWid(), w);
            }
        }

        // 3. 区分新增/更新
        int inserted = 0, updated = 0;
        List<Warehouse> toInsert = new ArrayList<>();
        List<Warehouse> toUpdate = new ArrayList<>();

        for (Map<String, Object> row : rows)
        {
            Integer wid = getInt(row, "wid", "warehouse_id", "id");
            if (wid == null) continue;

            // 跳过已删除仓库
            Integer isDelete = getInt(row, "is_delete", "isDelete");
            if (isDelete != null && isDelete != 0) continue;

            Warehouse entity = existing.get(wid);
            boolean isNew = (entity == null);
            if (isNew)
            {
                entity = new Warehouse();
                entity.setWid(wid);
            }

            // 映射字段
            entity.setName(getString(row, "name"));
            entity.setType(getInt(row, "type"));
            entity.setSubType(getInt(row, "sub_type", "subType"));
            entity.setIsDelete(isDelete != null ? isDelete : 0);
            entity.setCountryCode(getString(row, "country_code", "countryCode"));
            entity.setWpId(getInt(row, "wp_id", "wpId"));
            entity.setWpName(getString(row, "wp_name", "wpName"));
            entity.settWarehouseName(getString(row, "t_warehouse_name", "tWarehouseName"));
            entity.settWarehouseCode(getString(row, "t_warehouse_code", "tWarehouseCode"));
            entity.settCountryAreaName(getString(row, "t_country_area_name", "tCountryAreaName"));
            entity.settStatus(getInt(row, "t_status", "tStatus"));

            if (isNew)
            {
                toInsert.add(entity);
                inserted++;
            }
            else
            {
                toUpdate.add(entity);
                updated++;
            }
        }

        // 4. 批量写入
        if (!toInsert.isEmpty())
        {
            warehouseMapper.batchInsert(toInsert);
        }
        for (Warehouse w : toUpdate)
        {
            warehouseMapper.updateWarehouse(w);
        }

        return new int[]{inserted, updated};
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> getDataList(Map<String, Object> resp)
    {
        if (resp == null) return new ArrayList<>();
        Object data = resp.get("data");
        if (data == null) return new ArrayList<>();
        if (data instanceof List)
        {
            return (List<Map<String, Object>>) data;
        }
        try
        {
            // 可能是领星返回的嵌套结构: {"code":0, "data": [...]} 直接传了数组
            List<Map<String, Object>> converted = objectMapper.convertValue(data,
                    new TypeReference<List<Map<String, Object>>>() {});
            return converted != null ? converted : new ArrayList<>();
        }
        catch (Exception e)
        {
            LOG.warn("解析仓库列表 data 字段失败, data类型={}: {}",
                    data.getClass().getName(), e.getMessage());
            return new ArrayList<>();
        }
    }

    private String getString(Map<String, Object> map, String... keys)
    {
        for (String k : keys)
        {
            Object v = map.get(k);
            if (v != null && StringUtils.hasText(String.valueOf(v)))
            {
                return String.valueOf(v);
            }
        }
        return null;
    }

    private Integer getInt(Map<String, Object> map, String... keys)
    {
        String s = getString(map, keys);
        if (s == null) return null;
        try { return Integer.valueOf(s); }
        catch (Exception e) { return null; }
    }
}
