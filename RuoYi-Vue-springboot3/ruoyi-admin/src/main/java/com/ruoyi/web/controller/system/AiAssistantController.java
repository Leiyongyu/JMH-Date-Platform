package com.ruoyi.web.controller.system;

import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.utils.SecurityUtils;
import com.ruoyi.system.service.ai.AiAssistantPythonClient;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.Map;
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

    public AiAssistantController(AiAssistantPythonClient pythonClient)
    {
        this.pythonClient = pythonClient;
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
}
