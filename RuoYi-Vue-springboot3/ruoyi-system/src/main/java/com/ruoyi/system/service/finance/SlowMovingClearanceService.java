package com.ruoyi.system.service.finance;

import com.ruoyi.system.mapper.operation.external.AmzFbaInventoryAgeGroupSummaryMapper;
import java.time.YearMonth;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Service;

/** 财务中心滞销清货数据查询。 */
@Service
public class SlowMovingClearanceService
{
    private final AmzFbaInventoryAgeGroupSummaryMapper mapper;

    public SlowMovingClearanceService(
            AmzFbaInventoryAgeGroupSummaryMapper mapper)
    {
        this.mapper = mapper;
    }

    public List<Map<String, Object>> list(String pullMonth)
    {
        return mapper.selectList(normalizeMonth(pullMonth));
    }

    public Map<String, Object> summary(String pullMonth)
    {
        String month = normalizeMonth(pullMonth);
        Map<String, Object> result = mapper.selectSummary(month);
        if (result != null) return result;

        Map<String, Object> empty = new LinkedHashMap<>();
        empty.put("pull_month",
                month != null ? month : mapper.selectLatestPullMonth());
        empty.put("group_count", 0);
        empty.put("inventory_0_90_qty", 0);
        empty.put("inventory_0_90_cost", 0);
        empty.put("inventory_91_180_qty", 0);
        empty.put("inventory_91_180_cost", 0);
        empty.put("inventory_181_plus_qty", 0);
        empty.put("inventory_181_plus_cost", 0);
        empty.put("total_inventory_qty", 0);
        empty.put("total_inventory_cost", 0);
        empty.put("pulled_at", null);
        return empty;
    }

    private String normalizeMonth(String value)
    {
        String month = trim(value);
        if (month == null) return null;
        try
        {
            return YearMonth.parse(month).toString();
        }
        catch (Exception e)
        {
            throw new IllegalArgumentException("拉取月份格式必须为YYYY-MM");
        }
    }

    private String trim(String value)
    {
        if (value == null) return null;
        String result = value.trim();
        return result.isEmpty() ? null : result;
    }
}
