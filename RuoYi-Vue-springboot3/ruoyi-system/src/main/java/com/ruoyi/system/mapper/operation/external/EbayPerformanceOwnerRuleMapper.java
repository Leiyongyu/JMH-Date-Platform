package com.ruoyi.system.mapper.operation.external;

import com.ruoyi.system.domain.operation.external.EbayPerformanceOwnerRule;
import java.util.List;
import java.util.Map;
import org.apache.ibatis.annotations.Param;

/** eBay 月度绩效品牌负责人规则 Mapper。 */
public interface EbayPerformanceOwnerRuleMapper
{
    int upsertBatch(@Param("rows") List<EbayPerformanceOwnerRule> rows);

    List<Map<String, Object>> selectSummaryByMonth(@Param("statMonth") String statMonth);
}
