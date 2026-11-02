package com.ruoyi.web.controller.system;

import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.utils.SecurityUtils;
import com.ruoyi.system.service.ai.AiAssistantPythonClient;
import com.ruoyi.system.service.operation.scope.BusinessDataScope;
import com.ruoyi.system.service.operation.scope.BusinessDataScopeService;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** ERP顶部AI助手，安全代理Python DeepSeek服务。 */
@Tag(name = "系统-AI助手")
@RestController
@RequestMapping("/system/ai-assistant")
public class AiAssistantController extends BaseController
{
    private final AiAssistantPythonClient pythonClient;
    private final BusinessDataScopeService dataScope;

    public AiAssistantController(AiAssistantPythonClient pythonClient, BusinessDataScopeService dataScope)
    {
        this.pythonClient = pythonClient;
        this.dataScope = dataScope;
    }

    @GetMapping("/status")
    public AjaxResult status(
            @RequestHeader(value = "X-Request-ID", required = false)
            String requestId)
    {
        return success(pythonClient.status(requestId));
    }

    @PostMapping("/chats")
    public AjaxResult chat(
            @RequestBody Map<String, Object> payload,
            @RequestHeader(value = "X-Request-ID", required = false)
            String requestId)
    {
        return success(pythonClient.chat(
                payload, SecurityUtils.getUserId(), SecurityUtils.getUsername(), requestId));
    }

    @GetMapping("/conversations")
    public AjaxResult conversations(
            @RequestHeader(value = "X-Request-ID", required = false)
            String requestId)
    {
        return success(pythonClient.listConversations(
                SecurityUtils.getUserId(), SecurityUtils.getUsername(), requestId));
    }

    @GetMapping("/conversations/{conversationId}")
    public AjaxResult conversation(
            @PathVariable String conversationId,
            @RequestHeader(value = "X-Request-ID", required = false)
            String requestId)
    {
        return success(pythonClient.getConversation(
                conversationId, SecurityUtils.getUserId(), SecurityUtils.getUsername(), requestId));
    }

    @PostMapping("/conversations")
    public AjaxResult createConversation(
            @RequestBody Map<String, Object> payload,
            @RequestHeader(value = "X-Request-ID", required = false)
            String requestId)
    {
        return success(pythonClient.createConversation(
                payload, SecurityUtils.getUserId(), SecurityUtils.getUsername(), requestId));
    }

    @DeleteMapping("/conversations/{conversationId}")
    public AjaxResult deleteConversation(
            @PathVariable String conversationId,
            @RequestHeader(value = "X-Request-ID", required = false)
            String requestId)
    {
        return success(pythonClient.deleteConversation(
                conversationId, SecurityUtils.getUserId(), SecurityUtils.getUsername(), requestId));
    }

    /** 数据助手：后台规划并调用只读业务工具，立即返回 runId 供前端轮询。 */
    @PostMapping("/agent-runs")
    public AjaxResult startAgentRun(
            @RequestBody Map<String, Object> payload,
            @RequestHeader(value = "X-Request-ID", required = false)
            String requestId)
    {
        Map<String, Object> body = new LinkedHashMap<>(payload == null ? Map.of() : payload);
        // 始终用登录用户的权限覆盖，不采用前端传入的 access。
        body.put("access", agentAccess());
        return success(pythonClient.startAgentRun(
                body, SecurityUtils.getUserId(), SecurityUtils.getUsername(), requestId));
    }

    @GetMapping("/agent-runs/{runId}")
    public AjaxResult agentRun(
            @PathVariable String runId,
            @RequestHeader(value = "X-Request-ID", required = false)
            String requestId)
    {
        return success(pythonClient.getAgentRun(
                UUID.fromString(runId).toString(), SecurityUtils.getUserId(), SecurityUtils.getUsername(), requestId));
    }

    @GetMapping("/memories")
    public AjaxResult memories(
            @RequestHeader(value = "X-Request-ID", required = false)
            String requestId)
    {
        return success(pythonClient.listMemories(
                SecurityUtils.getUserId(), SecurityUtils.getUsername(), requestId));
    }

    @DeleteMapping("/memories/{memoryId}")
    public AjaxResult deleteMemory(
            @PathVariable long memoryId,
            @RequestHeader(value = "X-Request-ID", required = false)
            String requestId)
    {
        return success(pythonClient.deleteMemory(
                memoryId, SecurityUtils.getUserId(), SecurityUtils.getUsername(), requestId));
    }

    Map<String, Object> agentAccess()
    {
        Set<String> permissions = SecurityUtils.getLoginUser().getPermissions();
        Map<String, Object> scopes = new LinkedHashMap<>();
        for (String module : new String[] { BusinessDataScopeService.EBAY, BusinessDataScopeService.AMZ })
        {
            BusinessDataScope scope = dataScope.resolve(SecurityUtils.getUserId(), module);
            // JSON null 表示全部数据，空列表表示无数据，与补货接口的 allowed_principals 约定一致。
            scopes.put(module, scope.isAll() ? null : new ArrayList<>(scope.getOwners()));
        }
        Map<String, Object> access = new LinkedHashMap<>();
        access.put("permissions", permissions == null ? new ArrayList<>() : new ArrayList<>(permissions));
        access.put("scopes", scopes);
        return access;
    }
}
