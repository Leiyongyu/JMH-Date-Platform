package com.ruoyi.system.mapper.procurement;

import com.ruoyi.system.domain.procurement.PendingPurchase;
import java.util.List;
import org.apache.ibatis.annotations.Param;

public interface PendingPurchaseMapper
{
    List<PendingPurchase> selectList(@Param("site") String site,
                                     @Param("sku") String sku,
                                     @Param("status") String status);

    int upsertPending(@Param("site") String site,
                      @Param("sku") String sku,
                      @Param("purchaseQuantity") Integer purchaseQuantity,
                      @Param("operator") String operator);

    List<PendingPurchase> selectPendingByIdsForUpdate(@Param("ids") List<Long> ids);

    int markPurchased(@Param("ids") List<Long> ids,
                      @Param("operator") String operator);
}
