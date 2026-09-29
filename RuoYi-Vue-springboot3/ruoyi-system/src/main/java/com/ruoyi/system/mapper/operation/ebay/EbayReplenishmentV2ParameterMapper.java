package com.ruoyi.system.mapper.operation.ebay;

import com.ruoyi.system.domain.operation.ebay.EbayReplenishmentV2Parameter;
import java.util.List;
import org.apache.ibatis.annotations.Param;

public interface EbayReplenishmentV2ParameterMapper
{
    List<EbayReplenishmentV2Parameter> selectAll(@Param("lock") boolean lock);

    int updateValue(@Param("row") EbayReplenishmentV2Parameter row,
                    @Param("operator") String operator);
}
