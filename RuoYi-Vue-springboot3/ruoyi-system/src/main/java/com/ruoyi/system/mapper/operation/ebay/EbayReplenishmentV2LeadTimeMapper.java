package com.ruoyi.system.mapper.operation.ebay;

import com.ruoyi.system.domain.operation.ebay.EbayReplenishmentV2LeadTime;
import java.util.List;
import org.apache.ibatis.annotations.Param;

public interface EbayReplenishmentV2LeadTimeMapper
{
    List<EbayReplenishmentV2LeadTime> selectByKeys(
            @Param("keys") List<EbayReplenishmentV2LeadTime> keys);

    int upsertField(@Param("site") String site,
                    @Param("sku") String sku,
                    @Param("field") String field,
                    @Param("days") Integer days,
                    @Param("operator") String operator);
}
