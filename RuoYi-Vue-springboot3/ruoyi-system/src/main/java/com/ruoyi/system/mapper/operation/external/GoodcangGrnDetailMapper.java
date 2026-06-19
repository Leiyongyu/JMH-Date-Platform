package com.ruoyi.system.mapper.operation.external;

import java.util.List;
import org.apache.ibatis.annotations.Param;
import com.ruoyi.system.domain.operation.external.GoodcangGrnDetail;

public interface GoodcangGrnDetailMapper
{
    List<GoodcangGrnDetail> selectAll();
    int deleteByReceivingCode(@Param("receivingCode") String receivingCode);
    int batchInsert(@Param("list") List<GoodcangGrnDetail> list);
}
