package com.ruoyi.system.mapper.operation.customs;

import com.ruoyi.system.domain.operation.customs.CustomsDeclarationGenerateLog;
import java.util.List;
import java.util.Map;
import org.apache.ibatis.annotations.Param;

public interface CustomsDeclarationGenerateLogMapper
{
    int batchUpsert(@Param("logs") List<CustomsDeclarationGenerateLog> logs);

    List<Map<String, Object>> selectBucketSummary(@Param("keys") List<Map<String, String>> keys);

    List<CustomsDeclarationGenerateLog> selectRecentLogs(@Param("keys") List<Map<String, String>> keys);
}
