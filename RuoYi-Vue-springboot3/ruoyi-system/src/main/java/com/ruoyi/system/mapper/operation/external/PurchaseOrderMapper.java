package com.ruoyi.system.mapper.operation.external;

import java.util.List;
import com.ruoyi.system.domain.operation.external.PurchaseOrder;

public interface PurchaseOrderMapper
{
    List<PurchaseOrder> selectAll();
    int insert(PurchaseOrder entity);
    int updateById(PurchaseOrder entity);
}
