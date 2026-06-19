package com.ruoyi.system.mapper.operation.external;

import com.ruoyi.system.domain.operation.external.AmzProductListing;
import org.apache.ibatis.annotations.Param;
import java.util.List;

public interface AmzProductListingMapper
{
    List<AmzProductListing> selectBySidSellerSku(@Param("sid") Integer sid, @Param("sellerSku") String sellerSku);
    int insert(AmzProductListing entity);
    int updateById(AmzProductListing entity);
    int batchInsert(@Param("list") List<AmzProductListing> list);
    int deleteAll();
}
