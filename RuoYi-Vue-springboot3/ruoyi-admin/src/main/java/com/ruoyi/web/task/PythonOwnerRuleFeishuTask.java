package com.ruoyi.web.task;

import com.ruoyi.system.service.finance.PythonPerformanceSchedulerClient;
import com.ruoyi.system.service.operation.IOperationSyncLogService;
import com.ruoyi.system.service.operation.sync.OperationSyncContext;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import java.util.Map;
import java.util.UUID;
import org.springframework.stereotype.Component;

/**
 * 负责人映射表飞书同步：每周一 08:00 检查飞书多维表格，内容有变化才入库，只重算负责人有变化的月份的绩效。
 * 负责人只在飞书维护，ERP 不再提供上传入口；需要立即生效时在定时任务页面对本任务「执行一次」。
 */
@Component("pythonOwnerRuleFeishuTask")
public class PythonOwnerRuleFeishuTask
{
    private static final String CODE = "owner_rule_feishu_sync";
    private static final String NAME = "负责人映射表飞书同步";
    private static final String PATH = "/api/v1/internal/scheduler/tasks/" + CODE + "/run";
    private final PythonPerformanceSchedulerClient client;
    private final IOperationSyncLogService logs;

    public PythonOwnerRuleFeishuTask(PythonPerformanceSchedulerClient client, IOperationSyncLogService logs)
    {
        this.client = client;
        this.logs = logs;
    }

    public void runWeekly()
    {
        long started = System.currentTimeMillis();
        String requestId = "quartz-owner-rule-feishu-" + UUID.randomUUID();
        Long logId = logs.start(CODE, NAME, PATH, "JOB", "SYSTEM", null, null);
        try
        {
            Map<String, Object> response = client.runOwnerRuleFeishu(requestId);
            Map<?, ?> data = (Map<?, ?>) response.get("data");
            Map<?, ?> details = (Map<?, ?>) data.get("result");
            int fetched = ((Number) details.get("fetched_rows")).intValue();
            int stored = ((Number) details.get("imported_rows")).intValue();
            boolean unchanged = "unchanged".equals(details.get("status"));
            // 内容未变是正常情况，不能按「入库 0 条」判成失败
            OperationSyncResult result = OperationSyncResult.successAllowEmpty(CODE, NAME, PATH,
                    fetched, unchanged ? fetched : stored, System.currentTimeMillis() - started);
            result.setDetails(response);
            result.setBusinessSummary(unchanged
                    ? "飞书内容与上次相同，未入库；飞书行数=" + fetched + "；requestId=" + requestId
                    : "飞书行数=" + fetched + "；规则=" + stored + "；负责人有变化的月份=" + details.get("changed_months")
                    + "；已重算绩效月份=" + details.get("refreshed_months") + "；requestId=" + requestId);
            logs.finish(logId, result);
            OperationSyncContext.set(result);
        }
        catch (Exception e)
        {
            OperationSyncResult result = OperationSyncResult.failed(CODE, NAME, PATH,
                    "requestId=" + requestId + "；" + e.getMessage(), System.currentTimeMillis() - started);
            logs.finish(logId, result);
            OperationSyncContext.set(result);
            throw new IllegalStateException("负责人映射表飞书同步失败，requestId=" + requestId, e);
        }
    }
}
