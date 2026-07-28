package com.ruoyi.system.service.finance;

import com.ruoyi.system.mapper.operation.external.CombinedPerformanceRankingMapper;
import java.time.YearMonth;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 财务中心 AMZ 与 eBay 统一月度绩效排名。 */
@Service
public class CombinedPerformanceRankingService
{
    private final CombinedPerformanceRankingMapper mapper;
    private final PerformanceRankingService amzService;
    private final EbayPerformanceRankingService ebayService;

    public CombinedPerformanceRankingService(
            CombinedPerformanceRankingMapper mapper,
            PerformanceRankingService amzService,
            EbayPerformanceRankingService ebayService)
    {
        this.mapper = mapper;
        this.amzService = amzService;
        this.ebayService = ebayService;
    }

    public List<Map<String, Object>> list(String statMonth, String principalName)
    {
        return mapper.selectList(statMonth, principalName);
    }

    /**
     * 先分别执行两套既有负责人匹配，再按月份和负责人合并两个平台的结果。
     */
    @Transactional(rollbackFor = Exception.class)
    public Map<String, Object> refresh(String statMonth)
    {
        String targetMonth = statMonth;
        if (targetMonth == null || targetMonth.isBlank())
            targetMonth = mapper.selectLatestSourceMonth();
        if (targetMonth == null || targetMonth.isBlank())
            throw new IllegalStateException("AMZ和eBay月度利润表均暂无可计算的数据");
        try
        {
            YearMonth.parse(targetMonth);
        }
        catch (Exception e)
        {
            throw new IllegalArgumentException("统计月份格式必须为YYYY-MM");
        }

        int amzProfitRows = mapper.countAmzProfitRows(targetMonth);
        int ebayProfitRows = mapper.countEbayProfitRows(targetMonth);
        if (amzProfitRows == 0 && ebayProfitRows == 0)
            throw new IllegalStateException(targetMonth + "暂无AMZ或eBay利润数据");

        Map<String, Object> amzResult = null;
        Map<String, Object> ebayResult = null;
        if (amzProfitRows > 0)
            amzResult = amzService.refresh(targetMonth);
        if (ebayProfitRows > 0)
            ebayResult = ebayService.refresh(targetMonth);

        mapper.deleteByStatMonth(targetMonth);
        int rows = mapper.rebuildByStatMonth(targetMonth);

        int sourceRows = intValue(amzResult, "sourceRows")
                + intValue(ebayResult, "sourceRows");
        int unmatchedRows = intValue(amzResult, "unmatchedRows")
                + intValue(ebayResult, "unmatchedRows");

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("statMonth", targetMonth);
        result.put("rows", rows);
        result.put("sourceRows", sourceRows);
        result.put("matchedRows", sourceRows - unmatchedRows);
        result.put("unmatchedRows", unmatchedRows);
        result.put("amzProfitRows", amzProfitRows);
        result.put("ebayProfitRows", ebayProfitRows);
        result.put("amzRankingRows", intValue(amzResult, "rows"));
        result.put("ebayRankingRows", intValue(ebayResult, "rows"));
        return result;
    }

    private int intValue(Map<String, Object> values, String key)
    {
        if (values == null) return 0;
        Object value = values.get(key);
        return value instanceof Number ? ((Number) value).intValue() : 0;
    }
}
