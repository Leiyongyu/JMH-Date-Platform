package com.ruoyi.system.service.operation.external.lingxing;

import java.util.Map;
import org.springframework.stereotype.Service;

@Service
public class LingxingGatewayService
{
    private final LingxingAuthService authService;
    private final LingxingOpenApiClient client;

    public LingxingGatewayService(LingxingAuthService authService, LingxingOpenApiClient client)
    {
        this.authService = authService;
        this.client = client;
    }

    public Map<String, Object> post(String path, Map<String, Object> body) throws Exception
    {
        return client.postSigned(path, body, authService.getAccessToken());
    }
}
