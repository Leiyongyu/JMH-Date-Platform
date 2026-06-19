package com.ruoyi.system.mapper.operation.external;

import com.ruoyi.system.domain.operation.external.AmzWarehouseInventoryDetail;
import org.apache.ibatis.annotations.Param;
import java.util.List;

public interface AmzWarehouseInventoryDetailMapper
{
    List<AmzWarehouseInventoryDetail> selectByWidSku(@Param("wid") Integer wid, @Param("sku") String sku);
    int insert(AmzWarehouseInventoryDetail entity);
    int updateById(AmzWarehouseInventoryDetail entity);
    int batchInsert(@Param("list") List<AmzWarehouseInventoryDetail> list);
    int deleteAll();
}
