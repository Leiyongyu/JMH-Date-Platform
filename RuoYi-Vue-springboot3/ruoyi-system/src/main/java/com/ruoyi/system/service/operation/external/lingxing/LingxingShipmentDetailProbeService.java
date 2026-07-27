package com.ruoyi.system.service.operation.external.lingxing;

import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

/**
 * 领星FBA发货单详情只读探针。
 *
 * <p>仅用于确认接口完整原始返回结构，不写数据库，也不调用任何更新接口。</p>
 */
@Service
public class LingxingShipmentDetailProbeService
{
    private static final String API_PATH =
            "erp/sc/routing/storage/shipment/getInboundShipmentListMwsDetail";
    private static final String DEFAULT_SHIPMENT_SN = "SP260715005";

    private final LingxingApiProbeService apiProbeService;

    public LingxingShipmentDetailProbeService(LingxingApiProbeService apiProbeService)
    {
        this.apiProbeService = apiProbeService;
    }

    public Map<String, Object> queryAndSave(String shipmentSn) throws Exception
    {
        String normalizedShipmentSn = StringUtils.hasText(shipmentSn)
                ? shipmentSn.trim() : DEFAULT_SHIPMENT_SN;

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("shipment_sn", normalizedShipmentSn);
        body.put("return_deleted", false);

        Map<String, Object> result = apiProbeService.queryAndSave(
                "shipment-detail", normalizedShipmentSn, API_PATH, body);
        result.put("shipmentSn", normalizedShipmentSn);
        return result;
    }
}
