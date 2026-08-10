package com.ruoyi.system.service.ai;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.common.exception.ServiceException;
import com.ruoyi.system.service.finance.PythonHttpSupport;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

/** 调用受内部令牌保护的Python DeepSeek AI助手接口。 */
@Service
public class AiAssistantPythonClient extends PythonHttpSupport
{
    private static final String SERVICE_NAME = "Python AI助手";

    public AiAssistantPythonClient(
            AiAssistantPythonProperties properties,
            ObjectMapper objectMapper)
    {
        super(properties, objectMapper);
    }

    public Object status(String requestId)
    {
        try
        {
            HttpRequest request = baseRequest(
                    "/api/v1/ai-assistant/status", requestId)
                    .GET()
                    .build();
            return send(request);
        }
        catch (Exception e)
        {
            throw failure(e);
        }
    }

    public Object chat(
            Map<String, Object> payload,
            Long erpUserId,
            String erpUser,
            String requestId)
    {
        try
        {
            String body = objectMapper.writeValueAsString(
                    payload == null ? Map.of() : payload);
            HttpRequest.Builder builder = userRequest(
                    "/api/v1/ai-assistant/chats", erpUserId, erpUser, requestId)
                    .header("Content-Type", "application/json;charset=utf-8");
            return send(builder.POST(
                    HttpRequest.BodyPublishers.ofString(
                            body, StandardCharsets.UTF_8))
                    .build());
        }
        catch (Exception e)
        {
            throw failure(e);
        }
    }

    public Object listConversations(Long erpUserId, String erpUser, String requestId)
    {
        try
        {
            return send(userRequest(
                    "/api/v1/ai-assistant/conversations",
                    erpUserId, erpUser, requestId).GET().build());
        }
        catch (Exception e)
        {
            throw failure(e);
        }
    }

    public Object getConversation(
            String conversationId, Long erpUserId, String erpUser, String requestId)
    {
        try
        {
            return send(userRequest(
                    "/api/v1/ai-assistant/conversations/" + conversationId,
                    erpUserId, erpUser, requestId).GET().build());
        }
        catch (Exception e)
        {
            throw failure(e);
        }
    }

    public Object createConversation(
            Map<String, Object> payload,
            Long erpUserId,
            String erpUser,
            String requestId)
    {
        try
        {
            String body = objectMapper.writeValueAsString(
                    payload == null ? Map.of() : payload);
            HttpRequest request = userRequest(
                    "/api/v1/ai-assistant/conversations",
                    erpUserId, erpUser, requestId)
                    .header("Content-Type", "application/json;charset=utf-8")
                    .POST(HttpRequest.BodyPublishers.ofString(
                            body, StandardCharsets.UTF_8))
                    .build();
            return send(request);
        }
        catch (Exception e)
        {
            throw failure(e);
        }
    }

    public Object deleteConversation(
            String conversationId, Long erpUserId, String erpUser, String requestId)
    {
        try
        {
            return send(userRequest(
                    "/api/v1/ai-assistant/conversations/" + conversationId,
                    erpUserId, erpUser, requestId).DELETE().build());
        }
        catch (Exception e)
        {
            throw failure(e);
        }
    }

    private HttpRequest.Builder userRequest(
            String path, Long erpUserId, String erpUser, String requestId)
    {
        HttpRequest.Builder builder = baseRequest(path, requestId);
        if (erpUserId != null)
            builder.header("X-Erp-User-ID", String.valueOf(erpUserId));
        if (StringUtils.hasText(erpUser))
            builder.header("X-Erp-User", erpUser.trim());
        return builder;
    }

    private Object send(HttpRequest request) throws Exception
    {
        HttpResponse<String> response = httpClient.send(
                request,
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
        Map<String, Object> body = parseJson(response.body());
        if (response.statusCode() >= 400)
            throw new ServiceException(
                    errorMessage(body, response.statusCode(), SERVICE_NAME));
        if (integer(body.get("code"), -1) != 0)
            throw new ServiceException(
                    SERVICE_NAME + "错误: " + body.getOrDefault("message", "unknown"));
        return body.get("data");
    }

    private ServiceException failure(Exception exception)
    {
        if (exception instanceof InterruptedException)
            Thread.currentThread().interrupt();
        if (exception instanceof ServiceException serviceException)
            return serviceException;
        return new ServiceException(
                SERVICE_NAME + "调用失败: " + exception.getMessage());
    }
}
