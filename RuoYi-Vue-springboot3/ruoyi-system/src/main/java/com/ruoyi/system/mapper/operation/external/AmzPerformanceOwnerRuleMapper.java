package com.ruoyi.system.mapper.operation.external;

import com.ruoyi.system.domain.operation.external.AmzPerformanceOwnerRule;
import java.util.List;
import java.util.Map;
import org.apache.ibatis.annotations.Param;

/** Amazon 月度绩效负责人规则 Mapper。 */
public interface AmzPerformanceOwnerRuleMapper
{
    int upsertBatch(@Param("rows") List<AmzPerformanceOwnerRule> rows);

    List<Map<String, Object>> selectSummaryByMonth(@Param("statMonth") String statMonth);
}
