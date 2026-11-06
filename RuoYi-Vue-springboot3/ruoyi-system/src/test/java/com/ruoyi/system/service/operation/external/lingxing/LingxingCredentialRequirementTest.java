package com.ruoyi.system.service.operation.external.lingxing;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

/**
 * application.yml 已移除凭据默认值，缺失时必须给出指向环境变量的明确报错，
 * 而不是把空 appId 当签名密钥用、报出看不懂的签名错误。
 */
class LingxingCredentialRequirementTest
{
    private LingxingAuthService service(String appId, String appSecret)
    {
        LingxingProperties properties = new LingxingProperties();
        properties.setAppId(appId);
        properties.setAppSecret(appSecret);
        return new LingxingAuthService(
                properties,
                mock(LingxingOpenApiClient.class),
                new ObjectMapper());
    }

    @Test void blankAppIdFailsWithActionableMessage()
    {
        LingxingAuthService auth = service("", "some-secret");
        IllegalStateException error =
                assertThrows(IllegalStateException.class, auth::getAccessToken);
        assertTrue(error.getMessage().contains("LINGXING_APP_ID"),
                error.getMessage());
        assertTrue(error.getMessage().contains("LINGXING_APP_SECRET"),
                error.getMessage());
    }

    @Test void blankAppSecretFailsToo()
    {
        LingxingAuthService auth = service("ak_something16chr", null);
        assertThrows(IllegalStateException.class, auth::getAccessToken);
    }

    @Test void tokenResponseEndpointIsGuardedAsWell()
    {
        LingxingAuthService auth = service(null, null);
        assertThrows(IllegalStateException.class, auth::getAccessTokenResponse);
    }

    @Test void configuredCredentialsPassTheGuard() throws Exception
    {
        // Reaching the client means the guard let the call through; the mocked
        // client returns an empty map, so token parsing fails afterwards.
        LingxingOpenApiClient client = mock(LingxingOpenApiClient.class);
        LingxingProperties properties = new LingxingProperties();
        // Shaped like a real APP ID (16 chars, used as the AES signing key)
        // but deliberately not a real one.
        properties.setAppId("ak_testappid1234");
        properties.setAppSecret("test-secret");
        LingxingAuthService auth =
                new LingxingAuthService(properties, client, new ObjectMapper());

        assertThrows(IllegalStateException.class, auth::getAccessToken);
        verify(client).postForm(eq("api/auth-server/oauth/access-token"), anyMap());
    }
}
