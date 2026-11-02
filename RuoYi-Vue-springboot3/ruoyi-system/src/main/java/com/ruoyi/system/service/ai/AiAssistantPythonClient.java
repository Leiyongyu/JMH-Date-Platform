package com.ruoyi.system.service.ai;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.common.exception.ServiceException;
import com.ruoyi.system.service.python.PythonHttpSupport;
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

    /** 提交数据助手后台任务；payload 中的 access 已由控制器按登录用户覆盖。 */
    public Object startAgentRun(
            Map<String, Object> payload,
            Long erpUserId,
            String erpUser,
            String requestId)
    {
        try
        {
            String body = objectMapper.writeValueAsString(payload);
            return send(userRequest("/api/v1/ai-assistant/agent-runs", erpUserId, erpUser, requestId)
                    .header("Content-Type", "application/json;charset=utf-8")
                    .POST(HttpRequest.BodyPublishers.ofString(body, StandardCharsets.UTF_8))
                    .build());
        }
        catch (Exception e)
        {
            throw failure(e);
        }
    }

    public Object getAgentRun(String runId, Long erpUserId, String erpUser, String requestId)
    {
        try
        {
            return send(userRequest("/api/v1/ai-assistant/agent-runs/" + runId,
                    erpUserId, erpUser, requestId).GET().build());
        }
        catch (Exception e)
        {
            throw failure(e);
        }
    }

    public Object listMemories(Long erpUserId, String erpUser, String requestId)
    {
        try
        {
            return send(userRequest("/api/v1/ai-assistant/memories",
                    erpUserId, erpUser, requestId).GET().build());
        }
        catch (Exception e)
        {
            throw failure(e);
        }
    }

    public Object deleteMemory(long memoryId, Long erpUserId, String erpUser, String requestId)
    {
        try
        {
            return send(userRequest("/api/v1/ai-assistant/memories/" + memoryId,
                    erpUserId, erpUser, requestId).DELETE().build());
        }
        catch (Exception e)
        {
            throw failure(e);
        }
    }

    public Object confirmMemory(long memoryId, Long erpUserId, String erpUser, String requestId)
    {
        return sendJson("POST", "/api/v1/ai-assistant/memories/" + memoryId + "/confirm", Map.of(),
                erpUserId, erpUser, requestId);
    }

    public Object saveFeedback(String runId, Map<String, Object> payload, Long erpUserId, String erpUser,
            String requestId)
    {
        return sendJson("POST", "/api/v1/ai-assistant/agent-runs/" + runId + "/feedback", payload,
                erpUserId, erpUser, requestId);
    }

    /** 全体用户的运行统计，调用方负责限制为管理员。 */
    public Object agentStats(int days, String requestId)
    {
        return sendJson("GET", "/api/v1/ai-assistant/agent-stats?days=" + days, null, null, null, requestId);
    }

    public Object listBriefs(Long erpUserId, String erpUser, String requestId)
    {
        return sendJson("GET", "/api/v1/ai-assistant/briefs", null, erpUserId, erpUser, requestId);
    }

    /** briefId 为空时新建，否则更新。 */
    public Object saveBrief(Long briefId, Map<String, Object> payload, Long erpUserId, String erpUser,
            String requestId)
    {
        return briefId == null
                ? sendJson("POST", "/api/v1/ai-assistant/briefs", payload, erpUserId, erpUser, requestId)
                : sendJson("PUT", "/api/v1/ai-assistant/briefs/" + briefId, payload, erpUserId, erpUser, requestId);
    }

    public Object deleteBrief(long briefId, Long erpUserId, String erpUser, String requestId)
    {
        return sendJson("DELETE", "/api/v1/ai-assistant/briefs/" + briefId, null, erpUserId, erpUser, requestId);
    }

    /** 执行简报；payload 含按该用户当前权限组装的 access 与 force（手动立即运行）。 */
    public Object runBrief(long briefId, Map<String, Object> payload, Long erpUserId, String erpUser,
            String requestId)
    {
        return sendJson("POST", "/api/v1/ai-assistant/briefs/" + briefId + "/run", payload,
                erpUserId, erpUser, requestId);
    }

    /** 到期待执行的简报：[{id, userId, username}]。 */
    public Object dueBriefs(String requestId)
    {
        return sendJson("GET", "/api/v1/ai-assistant/briefs-due", null, null, null, requestId);
    }

    private Object sendJson(String method, String path, Object payload, Long erpUserId, String erpUser,
            String requestId)
    {
        try
        {
            HttpRequest.Builder builder = userRequest(path, erpUserId, erpUser, requestId);
            if (payload == null)
                builder.method(method, HttpRequest.BodyPublishers.noBody());
            else
                builder.header("Content-Type", "application/json;charset=utf-8")
                        .method(method, HttpRequest.BodyPublishers.ofString(
                                objectMapper.writeValueAsString(payload), StandardCharsets.UTF_8));
            return send(builder.build());
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
