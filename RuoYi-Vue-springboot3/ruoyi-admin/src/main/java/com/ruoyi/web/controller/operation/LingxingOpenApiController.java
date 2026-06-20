package com.ruoyi.web.controller.operation;

import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.system.service.operation.external.lingxing.LingxingAuthService;
import com.ruoyi.system.service.operation.external.lingxing.LingxingGatewayService;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.security.access.prepost.PreAuthorize;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@Tag(name = "领星API")
@RestController
@RequestMapping("/operations/lingxing")
public class LingxingOpenApiController extends BaseController
{
    private final LingxingAuthService authService;
    private final LingxingGatewayService gatewayService;

    public LingxingOpenApiController(LingxingAuthService authService, LingxingGatewayService gatewayService)
    {
        this.authService = authService;
        this.gatewayService = gatewayService;
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
}
