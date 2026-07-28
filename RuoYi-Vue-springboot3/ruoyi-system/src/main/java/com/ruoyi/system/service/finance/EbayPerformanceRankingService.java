package com.ruoyi.system.service.finance;

import com.ruoyi.system.mapper.operation.external.EbayPerformanceRankingMapper;
import java.time.YearMonth;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 财务中心 eBay 月度绩效排名。 */
@Service
public class EbayPerformanceRankingService
{
    private final EbayPerformanceRankingMapper mapper;

    public EbayPerformanceRankingService(EbayPerformanceRankingMapper mapper)
    {
        this.mapper = mapper;
    }

    public List<Map<String, Object>> list(String statMonth, String principalName)
    {
        return mapper.selectList(statMonth, principalName);
    }

    @Transactional(rollbackFor = Exception.class)
    public Map<String, Object> refresh(String statMonth)
    {
        String targetMonth = statMonth;
        if (targetMonth == null || targetMonth.isBlank())
            targetMonth = mapper.selectLatestProfitMonth();
        if (targetMonth == null || targetMonth.isBlank())
            throw new IllegalStateException("eBay月度利润表暂无可计算的数据");
        try
        {
            YearMonth.parse(targetMonth);
        }
        catch (Exception e)
        {
            throw new IllegalArgumentException("统计月份格式必须为YYYY-MM");
        }

        mapper.deleteByStatMonth(targetMonth);
        int rows = mapper.rebuildByStatMonth(targetMonth);
        int sourceRows = mapper.countProfitRows(targetMonth);
        int unmatchedRows = mapper.countUnmatchedProfitRows(targetMonth);
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("statMonth", targetMonth);
        result.put("rows", rows);
        result.put("sourceRows", sourceRows);
        result.put("matchedRows", sourceRows - unmatchedRows);
        result.put("unmatchedRows", unmatchedRows);
        result.put("ruleCount", mapper.countOwnerRules(targetMonth));
        return result;
    }
}
