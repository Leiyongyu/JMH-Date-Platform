package com.ruoyi.system.mapper.operation.external;

import com.ruoyi.system.domain.operation.external.AmzFbaShipmentBox;
import org.apache.ibatis.annotations.Param;
import java.util.List;
import java.util.Map;

public interface AmzFbaShipmentBoxMapper
{
    int count();
    int deleteByShipmentId(String shipmentId);
    int batchInsert(List<AmzFbaShipmentBox> list);
    List<String> selectExistingShipmentIds(@Param("shipmentIds") List<String> shipmentIds);
    List<Map<String, Object>> selectSidByShipmentIds(@Param("shipmentIds") List<String> shipmentIds);

    /** 通过 amz_product_listing 映射 sku */
    int updateSkuFromListing();
}
