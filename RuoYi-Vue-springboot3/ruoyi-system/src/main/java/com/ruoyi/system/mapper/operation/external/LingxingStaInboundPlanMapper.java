package com.ruoyi.system.mapper.operation.external;

import com.ruoyi.system.domain.operation.external.LingxingStaInboundPlan;
import com.ruoyi.system.domain.operation.external.LingxingStaInboundPlanItem;
import com.ruoyi.system.domain.operation.external.LingxingStaInboundPlanShipment;
import com.ruoyi.system.domain.operation.external.LingxingStaPackingContext;
import java.util.List;
import org.apache.ibatis.annotations.Param;

public interface LingxingStaInboundPlanMapper
{
    int upsertPlan(LingxingStaInboundPlan plan);

    int deleteItemsByRecordKey(@Param("recordKey") String recordKey);

    int batchInsertItems(@Param("list") List<LingxingStaInboundPlanItem> items);

    int deleteShipmentsByRecordKey(@Param("recordKey") String recordKey);

    int batchInsertShipments(
            @Param("list") List<LingxingStaInboundPlanShipment> shipments);

    int countByInboundPlanId(@Param("inboundPlanId") String inboundPlanId);

    int countAllPlans();

    List<LingxingStaPackingContext> selectPackingContextByShipmentNo(
            @Param("shipmentNo") String shipmentNo);

    List<String> selectMskuBySkuOrMsku(
            @Param("recordKey") String recordKey,
            @Param("skuOrMsku") String skuOrMsku);

}
