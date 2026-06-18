package com.ruoyi.system.mapper.operation.external;

import java.math.BigDecimal;
import java.util.List;

import org.apache.ibatis.annotations.Param;

import com.ruoyi.system.domain.operation.external.EbayProductDedup;

public interface EbayProductDedupMapper
{
    List<EbayProductDedup> selectAll();
    int updateProfitRate(@Param("site") String site, @Param("middleCode") String middleCode, @Param("rate") BigDecimal rate);
    int updateReturnRate(@Param("site") String site, @Param("middleCode") String middleCode, @Param("rate") BigDecimal rate);
}
