package com.ruoyi.system.mapper.operation.external;

import com.ruoyi.system.domain.operation.external.EbayProductListing;
import org.apache.ibatis.annotations.Param;
import java.util.List;

public interface EbayProductListingMapper
{
    List<EbayProductListing> selectByItemIds(@Param("itemIds") List<String> itemIds);
    int batchInsert(@Param("list") List<EbayProductListing> list);
    int updateByItemId(EbayProductListing entity);
}
