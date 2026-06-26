package com.ruoyi.system.mapper.operation.external;

import com.ruoyi.system.domain.operation.external.AmzFbaShipmentBox;
import java.util.List;

public interface AmzFbaShipmentBoxMapper
{
    int deleteByShipmentId(String shipmentId);
    int batchInsert(List<AmzFbaShipmentBox> list);

    /** 通过 amz_product_listing 映射 sku */
    int updateSkuFromListing();
}
