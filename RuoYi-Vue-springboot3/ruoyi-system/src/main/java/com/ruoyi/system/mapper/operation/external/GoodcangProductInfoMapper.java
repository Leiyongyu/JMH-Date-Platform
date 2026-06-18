package com.ruoyi.system.mapper.operation.external;

import java.math.BigDecimal;
import java.util.List;

import org.apache.ibatis.annotations.Param;

import com.ruoyi.system.domain.operation.external.GoodcangProductInfo;

public interface GoodcangProductInfoMapper
{
    GoodcangProductInfo selectByMiddleCode(@Param("skuMiddle") String skuMiddle);
    List<GoodcangProductInfo> selectAll();
    int updatePrice(@Param("middleCode") String middleCode, @Param("price") BigDecimal price);
}
