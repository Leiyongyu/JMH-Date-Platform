package com.ruoyi.system.mapper.operation.external;

import java.util.List;

import org.apache.ibatis.annotations.Param;

import com.ruoyi.system.domain.operation.external.GoodcangProductInfo;

public interface GoodcangProductInfoMapper
{
    GoodcangProductInfo selectByMiddleCode(@Param("skuMiddle") String skuMiddle);
    List<GoodcangProductInfo> selectAll();
}
