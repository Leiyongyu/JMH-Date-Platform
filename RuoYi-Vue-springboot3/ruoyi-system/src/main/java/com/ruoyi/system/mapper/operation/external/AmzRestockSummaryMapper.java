package com.ruoyi.system.mapper.operation.external;

import com.ruoyi.system.domain.operation.external.AmzRestockSummary;
import org.apache.ibatis.annotations.Param;
import java.util.List;

public interface AmzRestockSummaryMapper
{
    List<AmzRestockSummary> selectByHashId(@Param("hashId") String hashId);
    int insert(AmzRestockSummary entity);
    int updateById(AmzRestockSummary entity);
    int batchInsert(@Param("list") List<AmzRestockSummary> list);
    int deleteAll();
}
