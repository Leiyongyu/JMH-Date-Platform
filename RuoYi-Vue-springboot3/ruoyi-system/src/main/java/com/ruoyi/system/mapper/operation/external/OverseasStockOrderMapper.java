package com.ruoyi.system.mapper.operation.external;

import com.ruoyi.system.domain.operation.external.OverseasStockOrder;
import java.util.List;

public interface OverseasStockOrderMapper
{
    List<OverseasStockOrder> selectAll();
    int insert(OverseasStockOrder entity);
    int updateById(OverseasStockOrder entity);
    OverseasStockOrder selectByOrderNo(String overseasOrderNo);
}
