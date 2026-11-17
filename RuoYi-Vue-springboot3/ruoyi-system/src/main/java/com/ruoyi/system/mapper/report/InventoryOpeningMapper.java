package com.ruoyi.system.mapper.report;

import com.ruoyi.system.domain.report.InventoryOpeningValue;
import java.util.List;
import org.apache.ibatis.annotations.Param;

/**
 * 查询 jmh_report.ads_monthly_opening_inventory_value (同 MySQL 实例，全限定表名)
 */
public interface InventoryOpeningMapper
{
    List<InventoryOpeningValue> selectList(@Param("vo") InventoryOpeningValue vo);

    List<InventoryOpeningValue> selectByReportDate(@Param("reportDate") String reportDate,
                                                    @Param("warehouseType") String warehouseType,
                                                    @Param("costStatus") String costStatus,
                                                    @Param("sku") String sku);
}
