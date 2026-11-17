package com.ruoyi.web.controller.operation;

import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.system.service.operation.customs.CustomsStaDeliveryDateService;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** STA送达时间查询阶段，仅提供查询，不注册提交修改接口。 */
@RestController
@RequestMapping("/operations/customs/shipment-fee/delivery-dates")
public class CustomsStaDeliveryDateController extends BaseController
{
    private final CustomsStaDeliveryDateService service;

    public CustomsStaDeliveryDateController(CustomsStaDeliveryDateService service) { this.service = service; }

    @PreAuthorize("@ss.hasPermi('customs:shipmentFee:list')")
    @PostMapping("/query")
    public AjaxResult query(@RequestBody Query request)
    {
        try
        {
            if (request == null) return error("查询参数不能为空");
            return success(service.query(request.inboundPlanId, request.shipmentNo, request.sid));
        }
        catch (Exception e) { return error(e.getMessage()); }
    }

    public static class Query
    {
        private String inboundPlanId;
        private String shipmentNo;
        private Long sid;
        public String getInboundPlanId() { return inboundPlanId; }
        public void setInboundPlanId(String value) { inboundPlanId = value; }
        public String getShipmentNo() { return shipmentNo; }
        public void setShipmentNo(String value) { shipmentNo = value; }
        public Long getSid() { return sid; }
        public void setSid(Long value) { sid = value; }
    }
}
