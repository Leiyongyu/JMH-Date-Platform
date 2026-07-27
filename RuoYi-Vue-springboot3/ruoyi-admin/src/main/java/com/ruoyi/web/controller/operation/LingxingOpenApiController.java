package com.ruoyi.web.controller.operation;

import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.system.service.operation.external.lingxing.LingxingAuthService;
import com.ruoyi.system.service.operation.external.lingxing.LingxingApiProbeService;
import com.ruoyi.system.service.operation.external.lingxing.LingxingGatewayService;
import com.ruoyi.system.service.operation.external.lingxing.LingxingLogisticsChannelSyncService;
import com.ruoyi.system.service.operation.external.lingxing.LingxingShipmentDetailProbeService;
import com.ruoyi.system.service.operation.external.lingxing.LingxingStaInboundPlanSyncService;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.security.access.prepost.PreAuthorize;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@Tag(name = "领星API")
@RestController
@RequestMapping("/operations/lingxing")
public class LingxingOpenApiController extends BaseController
{
    private final LingxingAuthService authService;
    private final LingxingGatewayService gatewayService;
    private final LingxingShipmentDetailProbeService shipmentDetailProbeService;
    private final LingxingApiProbeService apiProbeService;
    private final LingxingLogisticsChannelSyncService logisticsChannelSyncService;
    private final LingxingStaInboundPlanSyncService staInboundPlanSyncService;

    public LingxingOpenApiController(LingxingAuthService authService,
                                    LingxingGatewayService gatewayService,
                                    LingxingShipmentDetailProbeService shipmentDetailProbeService,
                                    LingxingApiProbeService apiProbeService,
                                    LingxingLogisticsChannelSyncService logisticsChannelSyncService,
                                    LingxingStaInboundPlanSyncService staInboundPlanSyncService)
    {
        this.authService = authService;
        this.gatewayService = gatewayService;
        this.shipmentDetailProbeService = shipmentDetailProbeService;
        this.apiProbeService = apiProbeService;
        this.logisticsChannelSyncService = logisticsChannelSyncService;
        this.staInboundPlanSyncService = staInboundPlanSyncService;
    }

    @PreAuthorize("@ss.hasPermi('operations:lingxing:test')")
    @PostMapping("/token/test")
    public AjaxResult testToken() throws Exception
    {
        String token = authService.getAccessToken();
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("ok", token != null && !token.isEmpty());
        data.put("tokenPrefix", token == null || token.length() < 8 ? "" : token.substring(0, 8));
        return success(data);
    }

    /** 测试拉取指定 seller_sku 的 AMZ listing */
    @PreAuthorize("@ss.hasPermi('operations:lingxing:test')")
    @PostMapping("/test-amz-sku")
    public AjaxResult testAmzSku(@RequestBody Map<String, String> req) throws Exception
    {
        String sku = req.getOrDefault("sellerSku", "LZY-US-STAR-BLACK-1");
        String sid = req.getOrDefault("sid", "");
        Map<String, Object> body = new LinkedHashMap<>();
        if (!sid.isEmpty()) body.put("sid", sid);
        else body.put("sid", "12531");
        body.put("is_pair", 1); body.put("is_delete", 0);
        body.put("search_field", "seller_sku");
        body.put("search_value", java.util.Collections.singletonList(sku));
        body.put("exact_search", 1);
        body.put("offset", 0); body.put("length", 10);
        return success(gatewayService.post("erp/sc/data/mws/listing", body));
    }

    /** 只读查询指定FBA发货单详情，并将领星完整原始响应格式化保存为TXT。 */
    @PreAuthorize("@ss.hasPermi('operations:lingxing:test')")
    @PostMapping("/shipment-detail/test")
    public AjaxResult testShipmentDetail(
            @RequestParam(defaultValue = "SP260506028") String shipmentSn) throws Exception
    {
        return success(shipmentDetailProbeService.queryAndSave(shipmentSn));
    }

    /** 只读测试领星本地库存物流渠道列表，并原样返回领星响应。 */
    @PreAuthorize("@ss.hasPermi('operations:lingxing:test')")
    @PostMapping("/local-inventory/channel-list/test")
    public AjaxResult testLocalInventoryChannelList(
            @RequestParam(defaultValue = "0") Integer offset,
            @RequestParam(defaultValue = "20") Integer length) throws Exception
    {
        int safeOffset = offset == null ? 0 : Math.max(offset, 0);
        int safeLength = length == null ? 20 : Math.min(Math.max(length, 1), 100);
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("offset", safeOffset);
        body.put("length", safeLength);
        return success(gatewayService.post("erp/sc/data/local_inventory/channelList", body));
    }

    /** 分页拉取全部头程物流渠道，校验完整后全量替换本地渠道表。 */
    @PreAuthorize("@ss.hasPermi('operations:lingxing:test')")
    @PostMapping("/logistics-channel/sync")
    public AjaxResult syncLogisticsChannels() throws Exception
    {
        return success(logisticsChannelSyncService.syncAll());
    }

    /** 最近一年按货件ID/货件单号精确查询STA任务，并保存任务与全部商品明细。 */
    @PreAuthorize("@ss.hasPermi('operations:lingxing:test')")
    @PostMapping("/sta-inbound-plan/sync")
    public AjaxResult syncStaInboundPlan(
            @RequestParam(defaultValue = "FBA19JSMN5B7") String shipmentId) throws Exception
    {
        return success(staInboundPlanSyncService.syncByShipmentId(shipmentId));
    }

    /**
     * 通用领星查询接口测试入口：传 API Path、请求体和文件标识，
     * 自动调用并把完整原始响应保存为 TXT。
     */
    @PreAuthorize("@ss.hasPermi('operations:lingxing:test')")
    @PostMapping("/api-test/query")
    public AjaxResult testQueryApi(@RequestBody LingxingApiTestRequest request) throws Exception
    {
        if (request == null)
        {
            return error("请求参数不能为空");
        }
        return success(apiProbeService.queryAndSave(
                request.getTestName(),
                request.getIdentifier(),
                request.getPath(),
                request.getBody()));
    }

    @PreAuthorize("@ss.hasPermi('operations:lingxing:call')")
    @PostMapping("/call")
    public AjaxResult call(@RequestBody LingxingCallRequest request) throws Exception
    {
        return success(gatewayService.post(request.getPath(), request.getBody()));
    }

    public static class LingxingCallRequest
    {
        private String path;
        private Map<String, Object> body = new LinkedHashMap<>();
        public String getPath() { return path; }
        public void setPath(String path) { this.path = path; }
        public Map<String, Object> getBody() { return body; }
        public void setBody(Map<String, Object> body) { this.body = body; }
    }

    public static class LingxingApiTestRequest
    {
        private String testName;
        private String identifier;
        private String path;
        private Map<String, Object> body = new LinkedHashMap<>();

        public String getTestName() { return testName; }
        public void setTestName(String testName) { this.testName = testName; }
        public String getIdentifier() { return identifier; }
        public void setIdentifier(String identifier) { this.identifier = identifier; }
        public String getPath() { return path; }
        public void setPath(String path) { this.path = path; }
        public Map<String, Object> getBody() { return body; }
        public void setBody(Map<String, Object> body) { this.body = body; }
    }
}
