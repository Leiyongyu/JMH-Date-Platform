package com.ruoyi.system.mapper.operation.external;

import java.util.List;

import org.apache.ibatis.annotations.Param;

import com.ruoyi.system.domain.operation.external.EbayPriceTrackingConfig;

public interface EbayPriceTrackingConfigMapper
{
    List<EbayPriceTrackingConfig> selectAll();

    EbayPriceTrackingConfig selectBySiteSku(@Param("site") String site, @Param("sku") String sku);

    int insert(EbayPriceTrackingConfig config);

    /** 乐观锁更新：WHERE version = #{version}，SET version = version + 1 */
    int updateWithVersion(EbayPriceTrackingConfig config);
}
