package com.ruoyi.system.mapper.operation.external;

import com.ruoyi.system.domain.operation.external.AmzFbaShipmentMark;
import org.apache.ibatis.annotations.Param;

public interface AmzFbaShipmentMarkMapper
{
    AmzFbaShipmentMark selectByMsku(@Param("msku") String msku);
    int upsert(AmzFbaShipmentMark mark);
    int confirm(@Param("msku") String msku);
}
