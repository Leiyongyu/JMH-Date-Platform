package com.ruoyi.web.task;

import com.ruoyi.system.service.finance.PythonPerformanceSchedulerClient;
import com.ruoyi.system.service.operation.IOperationSyncLogService;
import com.ruoyi.system.service.operation.sync.OperationSyncContext;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import com.ruoyi.system.service.operation.sync.SyncAlertService;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.stereotype.Component;

/** Quartz last calendar day, 09:00 Asia/Shanghai; always send the complete health report. */
@Component("pythonEbayTokenHealthTask")
public class PythonEbayTokenHealthTask
{
    private static final String CODE = "ebay_token_health_check";
    private static final String NAME = "eBay店铺密钥月末健康检查";
    private static final String PATH = "/api/v1/internal/scheduler/tasks/" + CODE + "/run";
    private final PythonPerformanceSchedulerClient client;
    private final IOperationSyncLogService logs;
    private final SyncAlertService alerts;

    public PythonEbayTokenHealthTask(PythonPerformanceSchedulerClient client, IOperationSyncLogService logs, SyncAlertService alerts)
    {
        this.client = client;
        this.logs = logs;
        this.alerts = alerts;
    }

    public void runMonthly()
    {
        long started = System.currentTimeMillis();
        String requestId = "quartz-ebay-health-" + UUID.randomUUID();
        Long logId = logs.start(CODE, NAME, PATH, "JOB", "SYSTEM", null, null);
        try
        {
            Map<String, Object> response = client.runEbayTokenHealth(requestId);
            Map<?, ?> data = (Map<?, ?>) response.get("data");
            Map<?, ?> report = (Map<?, ?>) data.get("result");
            List<String> messages = reportMessages(report);
            for (int i = 0; i < messages.size(); i++)
                if (!alerts.sendCredentialReminder("health:" + report.get("sync_batch_id") + ":" + i, messages.get(i)))
                    throw new IllegalStateException("健康报告未全部送达企微，请检查告警配置和发送状态");
            int count = ((Number) report.get("extract_rows")).intValue();
            OperationSyncResult result = OperationSyncResult.success(CODE, NAME, PATH,
                    count, count, System.currentTimeMillis() - started);
            result.setDetails(response);
            result.setBusinessSummary("检查完成且报告已发送；健康状态=" + report.get("summary")
                    + "；任务成功不代表所有密钥健康；requestId=" + requestId);
            logs.finish(logId, result);
            OperationSyncContext.set(result);
        }
        catch (Exception e)
        {
            // Do not append remote or transport exception text to persistent logs.
            OperationSyncResult result = OperationSyncResult.failed(CODE, NAME, PATH,
                    "健康检查或企微报告发送失败；请检查Python任务记录和企微配置；requestId=" + requestId,
                    System.currentTimeMillis() - started);
            logs.finish(logId, result);
            OperationSyncContext.set(result);
            throw new IllegalStateException("eBay健康检查或报告发送失败，requestId=" + requestId);
        }
    }

    static List<String> reportMessages(Map<?, ?> report)
    {
        if (!(report.get("accounts") instanceof List<?> accounts) || accounts.isEmpty()
                || !(report.get("summary") instanceof Map<?, ?> summary)
                || !(report.get("sync_batch_id") instanceof String))
            throw new IllegalStateException("健康报告结构不完整");
        String heading = "## eBay密钥健康月报\n检查时间：" + clean(report.get("checked_at"), 30) + "（北京时间）\n";
        StringBuilder text = new StringBuilder(heading);
        text.append("检查：").append(accounts.size()).append("家；缺密钥跳过：")
            .append(clean(report.get("skipped_rows"), 10)).append("家\n");
        for (String status : List.of("HEALTHY", "INVALID", "REVIEW", "MISMATCH", "SUSPICIOUS"))
            text.append(label(status)).append("：").append(summary.containsKey(status) ? summary.get(status) : 0).append("；");
        text.append("\n可疑数量不代表密钥失效；到期日为配置的预计日期。\n");
        List<String> messages = new ArrayList<>();
        for (Object item : accounts)
        {
            if (!(item instanceof Map<?, ?> row)) throw new IllegalStateException("健康报告行异常");
            String status = String.valueOf(row.get("status"));
            if (!List.of("HEALTHY", "INVALID", "REVIEW", "MISMATCH", "SUSPICIOUS").contains(status))
                throw new IllegalStateException("健康报告状态异常");
            String line = "- Excel第" + clean(row.get("source_row"), 8) + "行 " + clean(row.get("shop_name"), 45)
                    + "：" + label(status) + "；在售=" + clean(row.get("listing_count"), 16)
                    + "；上次=" + clean(row.get("previous_count"), 16)
                    + "；预计到期=" + clean(row.get("expires_on"), 10)
                    + "；剩余天数=" + clean(row.get("days_remaining"), 10)
                    + "；原因=" + clean(row.get("reason"), 65) + "\n";
            // WeCom markdown limit is bytes, not Java string length. Leave ample headroom.
            if ((text.toString() + line).getBytes(StandardCharsets.UTF_8).length > 3400)
            {
                messages.add(text.toString());
                text = new StringBuilder(heading + "（续）\n");
            }
            text.append(line);
        }
        messages.add(text.toString());
        return messages;
    }

    private static String label(String status)
    {
        return switch (status) {
            case "HEALTHY" -> "正常"; case "INVALID" -> "失效";
            case "MISMATCH" -> "账号不符"; case "SUSPICIOUS" -> "数量可疑"; default -> "待复查";
        };
    }

    private static String clean(Object value, int limit)
    {
        if (value == null) return "--";
        String safe = String.valueOf(value).replaceAll("[\\p{Cntrl}<>`*\\[\\]#]", " ");
        return safe.substring(0, Math.min(safe.length(), limit));
    }
}
