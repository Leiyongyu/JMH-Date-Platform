package com.ruoyi.web.task;

import com.ruoyi.common.core.domain.entity.SysUser;
import com.ruoyi.framework.web.service.SysPermissionService;
import com.ruoyi.system.service.ISysUserService;
import com.ruoyi.system.service.ai.AiAgentAccessBuilder;
import com.ruoyi.system.service.ai.AiAssistantPythonClient;
import com.ruoyi.system.service.operation.IOperationSyncLogService;
import com.ruoyi.system.service.operation.scope.BusinessDataScopeService;
import com.ruoyi.system.service.operation.sync.OperationSyncContext;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

/**
 * AI 数据助手定时简报：拉取到期的简报，按每个简报所属用户「当前」的菜单权限和数据范围逐个触发。
 * 用户已停用、删除时跳过；单个简报失败不影响其他简报。Python 侧按周期抢占，重复触发不会重复执行。
 */
@Component("aiBriefTask")
public class AiBriefTask
{
    private static final Logger log = LoggerFactory.getLogger(AiBriefTask.class);
    private static final String SYNC_TYPE = "ai_agent_brief";
    private static final String SYNC_NAME = "AI助手定时简报";
    private static final String API_PATH = "/api/v1/ai-assistant/briefs-due";
    private static final DateTimeFormatter REQUEST_TIME = DateTimeFormatter.ofPattern("yyyyMMddHHmmss");

    private final AiAssistantPythonClient client;
    private final ISysUserService userService;
    private final SysPermissionService permissionService;
    private final BusinessDataScopeService dataScope;
    private final IOperationSyncLogService logService;

    public AiBriefTask(AiAssistantPythonClient client, ISysUserService userService,
            SysPermissionService permissionService, BusinessDataScopeService dataScope,
            IOperationSyncLogService logService)
    {
        this.client = client;
        this.userService = userService;
        this.permissionService = permissionService;
        this.dataScope = dataScope;
        this.logService = logService;
    }

    public void runDue()
    {
        long started = System.currentTimeMillis();
        String requestId = "quartz-ai-brief-" + LocalDateTime.now().format(REQUEST_TIME) + "-"
                + UUID.randomUUID().toString().replace("-", "");
        Long logId = logService.start(SYNC_TYPE, SYNC_NAME, API_PATH, "JOB", "SYSTEM", null, null);
        List<Map<String, Object>> due;
        try
        {
            due = list(client.dueBriefs(requestId));
        }
        catch (Exception e)
        {
            OperationSyncResult failed = OperationSyncResult.failed(SYNC_TYPE, SYNC_NAME, API_PATH,
                    "requestId=" + requestId + "；" + e.getMessage(), System.currentTimeMillis() - started);
            logService.finish(logId, failed);
            OperationSyncContext.set(failed);
            throw new IllegalStateException("拉取到期简报失败，requestId=" + requestId + "：" + e.getMessage(), e);
        }
        int success = 0;
        int skipped = 0;
        List<String> errors = new ArrayList<>();
        for (Map<String, Object> brief : due)
        {
            long briefId = number(brief.get("id"));
            long userId = number(brief.get("userId"));
            try
            {
                SysUser user = userService.selectUserById(userId);
                if (user == null || !"0".equals(user.getStatus()) || !"0".equals(user.getDelFlag()))
                {
                    skipped++;
                    continue;
                }
                Map<String, Object> body = new LinkedHashMap<>();
                body.put("access", AiAgentAccessBuilder.build(
                        userId, permissionService.getMenuPermission(user), dataScope));
                body.put("force", false);
                client.runBrief(briefId, body, userId, user.getUserName(), requestId + "-" + briefId);
                success++;
            }
            catch (Exception e)
            {
                log.warn("AI简报执行失败 briefId={} userId={} requestId={}", briefId, userId, requestId, e);
                errors.add("简报" + briefId + "：" + e.getMessage());
            }
        }
        long elapsed = System.currentTimeMillis() - started;
        OperationSyncResult result = errors.isEmpty()
                ? OperationSyncResult.success(SYNC_TYPE, SYNC_NAME, API_PATH, due.size(), success, elapsed)
                : OperationSyncResult.failed(SYNC_TYPE, SYNC_NAME, API_PATH, String.join("；", errors), elapsed);
        result.setFailCount(errors.size());
        result.setBusinessSummary("到期" + due.size() + "个；已触发" + success + "个；跳过" + skipped
                + "个（用户停用/删除）；失败" + errors.size() + "个；requestId=" + requestId);
        logService.finish(logId, result);
        OperationSyncContext.set(result);
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> list(Object value)
    {
        List<Map<String, Object>> rows = new ArrayList<>();
        if (value instanceof List<?> items)
            for (Object item : items)
                if (item instanceof Map<?, ?>)
                    rows.add((Map<String, Object>) item);
        return rows;
    }

    private long number(Object value)
    {
        if (value instanceof Number n) return n.longValue();
        try { return Long.parseLong(String.valueOf(value)); }
        catch (Exception ignored) { return 0L; }
    }
}
