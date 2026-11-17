package com.ruoyi.web.controller.system;

import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.utils.SecurityUtils;
import com.ruoyi.system.service.ai.AiAgentAccessBuilder;
import com.ruoyi.system.service.ai.AiAssistantPythonClient;
import com.ruoyi.system.service.operation.scope.BusinessDataScopeService;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
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

    @PostMapping("/memories/{memoryId}/confirm")
    public AjaxResult confirmMemory(
            @PathVariable long memoryId,
            @RequestHeader(value = "X-Request-ID", required = false)
            String requestId)
    {
        return success(pythonClient.confirmMemory(
                memoryId, SecurityUtils.getUserId(), SecurityUtils.getUsername(), requestId));
    }

    @PostMapping("/agent-runs/{runId}/feedback")
    public AjaxResult feedback(
            @PathVariable String runId,
            @RequestBody Map<String, Object> payload,
            @RequestHeader(value = "X-Request-ID", required = false)
            String requestId)
    {
        return success(pythonClient.saveFeedback(UUID.fromString(runId).toString(),
                payload == null ? Map.of() : payload, SecurityUtils.getUserId(), SecurityUtils.getUsername(),
                requestId));
    }

    /** 运行看板：涵盖全体用户的提问记录，仅管理员可看。 */
    @PreAuthorize("@ss.hasRole('admin')")
    @GetMapping("/agent-stats")
    public AjaxResult agentStats(
            @RequestParam(defaultValue = "30") int days,
            @RequestHeader(value = "X-Request-ID", required = false)
            String requestId)
    {
        return success(pythonClient.agentStats(Math.max(1, Math.min(days, 180)), requestId));
    }

    Map<String, Object> agentAccess()
    {
        return AiAgentAccessBuilder.build(
                SecurityUtils.getUserId(), SecurityUtils.getLoginUser().getPermissions(), dataScope);
    }
}
