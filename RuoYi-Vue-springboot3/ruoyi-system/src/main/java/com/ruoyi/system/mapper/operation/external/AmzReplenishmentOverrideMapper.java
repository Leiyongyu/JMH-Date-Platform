package com.ruoyi.system.mapper.operation.external;

import org.apache.ibatis.annotations.Param;

import com.ruoyi.system.domain.operation.external.AmzReplenishmentOverride;

public interface AmzReplenishmentOverrideMapper
{
    AmzReplenishmentOverride selectBySidSku(@Param("sid") String sid, @Param("sellerSku") String sellerSku);
    int upsert(AmzReplenishmentOverride entity);
    int upsertProductCategory(AmzReplenishmentOverride entity);
    int upsertManualPurchasedQty(AmzReplenishmentOverride entity);
}
