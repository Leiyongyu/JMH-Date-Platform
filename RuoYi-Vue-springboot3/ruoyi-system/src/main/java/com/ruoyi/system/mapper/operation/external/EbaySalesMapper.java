package com.ruoyi.system.mapper.operation.external;

import java.util.List;
import java.util.Map;

import com.ruoyi.system.domain.operation.external.EbaySales;

public interface EbaySalesMapper
{
    List<EbaySales> selectAll();
    int batchUpsert(List<Map<String, Object>> list);
}
