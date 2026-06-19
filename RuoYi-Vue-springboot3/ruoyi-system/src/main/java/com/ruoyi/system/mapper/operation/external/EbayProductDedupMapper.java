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
    int updateLowestPrice(@Param("site") String site, @Param("sku") String sku, @Param("price") BigDecimal price);
    int updateTrackingCalc(@Param("site") String site, @Param("sku") String sku,
            @Param("trackingPrice") BigDecimal trackingPrice,
            @Param("trackingProfitMargin") BigDecimal trackingProfitMargin,
            @Param("floorPrice") BigDecimal floorPrice);
    int updateOeNumber(@Param("site") String site, @Param("sku") String sku, @Param("oeNumber") String oeNumber);
    int updateRemark(@Param("site") String site, @Param("sku") String sku, @Param("remark") String remark);

    /** 从 ebay_product_listing 重建去重表 */
    int rebuildFromListing();
}
