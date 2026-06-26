package com.ruoyi.system.mapper.operation.external;

import com.ruoyi.system.domain.operation.external.OverseasStockOrderDetail;
import java.util.List;
import org.apache.ibatis.annotations.Param;

public interface OverseasStockOrderDetailMapper
{
    int deleteByOrderNo(@Param("overseasOrderNo") String overseasOrderNo);
    int batchInsert(@Param("list") List<OverseasStockOrderDetail> list);
}
