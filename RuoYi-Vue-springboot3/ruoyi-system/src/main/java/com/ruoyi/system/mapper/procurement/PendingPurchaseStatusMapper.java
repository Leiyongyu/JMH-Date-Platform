package com.ruoyi.system.mapper.procurement;

import java.time.LocalDate;
import java.util.List;
import java.util.Map;
import org.apache.ibatis.annotations.Param;

public interface PendingPurchaseStatusMapper
{
    List<String> selectSkus();
    List<Map<String, Object>> selectWarehouses();
    Map<String, Object> selectState();
    int start();
    int fail();
    int publish(@Param("from") LocalDate from, @Param("to") LocalDate to, @Param("count") int count);
    int clearSnapshot();
    int insertRows(@Param("rows") List<Map<String, Object>> rows);
    List<Map<String, Object>> selectSummary(@Param("ids") List<Long> ids);
    List<Map<String, Object>> selectDetails(@Param("id") Long id);
}
