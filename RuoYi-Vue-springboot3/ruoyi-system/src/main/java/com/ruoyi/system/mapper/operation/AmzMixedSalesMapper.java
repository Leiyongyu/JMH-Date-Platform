package com.ruoyi.system.mapper.operation;

import com.ruoyi.system.domain.operation.AmzMixedSalesQuery;
import java.util.List;
import java.util.Map;
import org.apache.ibatis.annotations.Param;

public interface AmzMixedSalesMapper
{
    long countProducts(@Param("q") AmzMixedSalesQuery query);
    List<Map<String, Object>> selectProducts(@Param("q") AmzMixedSalesQuery query);
    long countDetails(@Param("q") AmzMixedSalesQuery query);
    List<Map<String, Object>> selectDetails(@Param("q") AmzMixedSalesQuery query);
    List<Map<String, Object>> selectStores();
}
