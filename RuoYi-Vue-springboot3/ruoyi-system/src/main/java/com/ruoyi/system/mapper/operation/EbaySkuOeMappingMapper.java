package com.ruoyi.system.mapper.operation;

import java.util.List;
import org.apache.ibatis.annotations.Param;
import com.ruoyi.system.domain.operation.ebay.EbaySkuOeMapping;

public interface EbaySkuOeMappingMapper
{
    List<String> selectExistingSkus(@Param("skus") List<String> skus);

    int deleteBySkus(@Param("skus") List<String> skus);

    int batchInsert(@Param("list") List<EbaySkuOeMapping> list);

    List<EbaySkuOeMapping> selectBySkus(@Param("skus") List<String> skus);
}
