package com.ruoyi.system.service.operation.sync;

import com.ruoyi.common.core.redis.RedisCache;
import com.ruoyi.common.utils.spring.SpringUtils;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Duration;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.TimeUnit;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

/**
 * 企业微信机器人同步告警（去重 + 恢复通知）。
 */
@Service
public class SyncAlertService
{
    private static final Logger LOG = LoggerFactory.getLogger(SyncAlertService.class);

    @Value("${sync.alert.enabled:true}")
    private boolean enabled;

    @Value("${sync.alert.webhook-url:}")
    private String webhookUrl;

    @Value("${sync.alert.notify-started:false}")
    private boolean notifyStarted;

    @Value("${sync.alert.notify-success:false}")
    private boolean notifySuccess;

    @Value("${sync.alert.notify-recovery:false}")
    private boolean notifyRecovery;

    @Value("${sync.alert.max-runtime-minutes:90}")
    private int maxRuntimeMinutes;

    private static final String ALERT_PREFIX = "alert:sent:";
    private static final int DEDUP_MINUTES = 60;
    private static final HttpClient HTTP = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(10)).build();
    private static final DateTimeFormatter DTF = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");
    private final Map<String, RunningJob> runningJobs = new ConcurrentHashMap<>();

    /** 发送失败告警（Redis 去重 60 分钟） */
    public void sendAlert(String chainCode, String stepCode, String status, String error, Long logId)
    {
        sendAlert(chainCode, stepCode, stepCode, "", status, error, logId);
    }

    /** 发送失败告警（Redis 去重 60 分钟） */
    public void sendAlert(String chainCode, String stepCode, String stepName, String apiPath,
                          String status, String error, Long logId)
    {
        if (!enabled)
        {
            LOG.warn("同步告警未发送：sync.alert.enabled=false，链路={}，步骤={}", chainCode, stepCode);
            return;
        }
        if (webhookUrl == null || webhookUrl.isBlank())
        {
            LOG.warn("同步告警未发送：sync.alert.webhook-url 为空，请配置环境变量 SYNC_ALERT_WEBHOOK_URL，链路={}，步骤={}，错误={}",
                    chainCode, stepCode, truncate(error, 200));
            return;
        }

        try { markFailed(chainCode, stepCode); }
        catch (Exception e) { LOG.warn("告警失败状态写入Redis失败，仍继续发送企微消息: {}", e.getMessage()); }
        String dedupKey = ALERT_PREFIX + chainCode + ":" + stepCode + ":" + hash(error);
        try
        {
            RedisCache redis = SpringUtils.getBean(RedisCache.class);
            if (!redis.setCacheObjectIfAbsent(dedupKey, "1", DEDUP_MINUTES, TimeUnit.MINUTES))
            { LOG.debug("告警已去重 {}", dedupKey); return; }
        }
        catch (Exception e)
        {
            // Redis故障本身可能就是同步失败原因，去重不得阻断企微告警。
            LOG.warn("企微告警Redis去重失败，将直接发送: {}", e.getMessage());
        }

        String content = "## ⚠️ 同步告警\n"
                + "> 链路：" + resolveName(chainCode) + "\n"
                + "> 步骤：" + stepName + " (" + stepCode + ")\n"
                + "> 接口：" + (apiPath != null ? apiPath : "") + "\n"
                + "> 状态：" + status + "\n"
                + "> 错误：" + truncate(error, 400) + "\n"
                + "> 时间：" + LocalDateTime.now().format(DTF) + "\n"
                + "> 日志ID：" + (logId != null ? String.valueOf(logId) : "");
        post(content);
    }

    /** Quartz全局任务开始通知。 */
    public void notifyQuartzJobStarted(
            String jobId, String jobName, String jobGroup, String invokeTarget)
    {
        runningJobs.put(safe(jobId), new RunningJob(
                safe(jobId), safe(jobName), safe(jobGroup), safe(invokeTarget),
                System.currentTimeMillis()));
        if (!canSend() || !notifyStarted) return;
        String content = "## 🚀 定时任务已开始\n"
                + "> 任务：" + safe(jobName) + "\n"
                + "> 分组：" + safe(jobGroup) + "\n"
                + "> 调用：" + safe(invokeTarget) + "\n"
                + "> 时间：" + LocalDateTime.now().format(DTF) + "\n"
                + "> 任务ID：" + safe(jobId);
        post(content);
    }

    /** Quartz全局任务结果通知；失败去重，下次成功自动标记恢复。 */
    public void notifyQuartzJobFinished(
            String jobId, String jobName, String jobGroup, String invokeTarget,
            boolean success, String detail, long runMs)
    {
        runningJobs.remove(safe(jobId));
        if (!canSend()) return;
        String stepCode = "job:" + safe(jobId);
        String failKey = ALERT_PREFIX + "quartz:" + stepCode + ":last_status";
        if (!success)
        {
            sendAlert("quartz", stepCode, jobName, invokeTarget,
                    "FAILED", detail, parseLong(jobId));
            return;
        }

        boolean recovered = consumeFailureFlag(failKey);
        if (!notifySuccess && !(notifyRecovery && recovered)) return;
        String content = notifyRecovery && recovered
                ? "## ✅ 定时任务已恢复\n"
                : "## ✅ 定时任务成功\n";
        content += "> 任务：" + safe(jobName) + "\n"
                + "> 分组：" + safe(jobGroup) + "\n"
                + "> 调用：" + safe(invokeTarget) + "\n"
                + "> 耗时：" + formatDuration(runMs) + "\n"
                + "> 结果：" + truncate(detail, 600) + "\n"
                + "> 时间：" + LocalDateTime.now().format(DTF) + "\n"
                + "> 任务ID：" + safe(jobId);
        post(content);
    }

    /** 非Quartz的Spring后台任务失败告警。 */
    public void notifyBackgroundFailure(String taskCode, String taskName, String error)
    {
        sendAlert("background", taskCode, taskName, "@Scheduled", "FAILED", error, null);
    }

    /** 非Quartz后台任务失败后的恢复通知。 */
    public void notifyBackgroundRecovery(String taskCode, String taskName)
    {
        checkAndSendRecovery("background", taskCode, taskName, null);
    }

    /** 每分钟检查已开始但长时间未结束的Quartz任务。 */
    @Scheduled(fixedRate = 60000L)
    public void watchRunningQuartzJobs()
    {
        if (maxRuntimeMinutes <= 0) return;
        long now = System.currentTimeMillis();
        long threshold = TimeUnit.MINUTES.toMillis(maxRuntimeMinutes);
        for (RunningJob job : runningJobs.values())
        {
            if (!job.warned && now - job.startedAt >= threshold)
            {
                job.warned = true;
                sendAlert("quartz_watchdog", "job:" + job.jobId,
                        job.jobName, job.invokeTarget, "TIMEOUT",
                        "任务开始后超过" + maxRuntimeMinutes
                                + "分钟仍未结束，可能出现接口卡死或线程阻塞；开始时间="
                                + LocalDateTime.ofInstant(
                                        java.time.Instant.ofEpochMilli(job.startedAt),
                                        java.time.ZoneId.systemDefault()).format(DTF),
                        parseLong(job.jobId));
            }
        }
    }

    /** 检查恢复：上次失败 + 本次成功 → 发恢复通知 */
    public void checkAndSendRecovery(String chainCode, String stepCode, Long currentLogId)
    {
        checkAndSendRecovery(chainCode, stepCode, stepCode, currentLogId);
    }

    public void checkAndSendRecovery(String chainCode, String stepCode, String stepName, Long currentLogId)
    {
        if (!enabled || webhookUrl == null || webhookUrl.isBlank()) return;
        // 恢复检测键
        String failKey = ALERT_PREFIX + chainCode + ":" + stepCode + ":last_status";
        if (!notifyRecovery)
        {
            consumeFailureFlag(failKey);
            return;
        }
        RedisCache redis = SpringUtils.getBean(RedisCache.class);
        Boolean wasFailed = redis.getCacheObject(failKey);
        if (Boolean.TRUE.equals(wasFailed))
        {
            String content = "## ✅ 已恢复\n"
                    + "> 链路：" + resolveName(chainCode) + "\n"
                    + "> 步骤：" + stepName + " (" + stepCode + ")\n"
                    + "> 日志ID：" + (currentLogId != null ? String.valueOf(currentLogId) : "") + "\n"
                    + "> 时间：" + LocalDateTime.now().format(DTF);
            post(content);
            redis.deleteObject(failKey);
        }
    }

    /** 标记步骤失败（供恢复检测用） */
    void markFailed(String chainCode, String stepCode)
    {
        RedisCache redis = SpringUtils.getBean(RedisCache.class);
        redis.setCacheObject(ALERT_PREFIX + chainCode + ":" + stepCode + ":last_status", Boolean.TRUE, 1440, TimeUnit.MINUTES);
    }

    private boolean canSend()
    {
        if (!enabled) return false;
        if (webhookUrl == null || webhookUrl.isBlank())
        {
            LOG.warn("企微通知未发送：sync.alert.webhook-url为空");
            return false;
        }
        return true;
    }

    private boolean consumeFailureFlag(String failKey)
    {
        try
        {
            RedisCache redis = SpringUtils.getBean(RedisCache.class);
            Boolean wasFailed = redis.getCacheObject(failKey);
            if (Boolean.TRUE.equals(wasFailed)) redis.deleteObject(failKey);
            return Boolean.TRUE.equals(wasFailed);
        }
        catch (Exception e)
        {
            LOG.warn("读取任务恢复状态失败: {}", e.getMessage());
            return false;
        }
    }

    private Long parseLong(String value)
    {
        try { return Long.valueOf(value); }
        catch (Exception ignored) { return null; }
    }

    private String safe(Object value)
    {
        return value == null ? "" : String.valueOf(value);
    }

    private String formatDuration(long runMs)
    {
        if (runMs < 1000) return runMs + "ms";
        long seconds = runMs / 1000;
        if (seconds < 60) return seconds + "秒";
        return (seconds / 60) + "分" + (seconds % 60) + "秒";
    }

    private static final class RunningJob
    {
        private final String jobId;
        private final String jobName;
        @SuppressWarnings("unused")
        private final String jobGroup;
        private final String invokeTarget;
        private final long startedAt;
        private volatile boolean warned;

        private RunningJob(String jobId, String jobName, String jobGroup,
                           String invokeTarget, long startedAt)
        {
            this.jobId = jobId;
            this.jobName = jobName;
            this.jobGroup = jobGroup;
            this.invokeTarget = invokeTarget;
            this.startedAt = startedAt;
        }
    }

    // ==================== 内部 ====================

    private void post(String markdown)
    {
        try
        {
            String json = "{\"msgtype\":\"markdown\",\"markdown\":{\"content\":\""
                    + markdown.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n") + "\"}}";
            HttpRequest req = HttpRequest.newBuilder(URI.create(webhookUrl))
                    .timeout(Duration.ofSeconds(30))
                    .header("Content-Type", "application/json; charset=utf-8")
                    .POST(HttpRequest.BodyPublishers.ofString(json, StandardCharsets.UTF_8)).build();
            HttpResponse<String> resp = HTTP.send(req, HttpResponse.BodyHandlers.ofString());
            if (resp.statusCode() != 200) LOG.warn("企微告警发送失败 HTTP{}: {}", resp.statusCode(), resp.body());
            else if (resp.body() == null || !resp.body().contains("\"errcode\":0"))
                LOG.warn("企微告警返回异常: {}", resp.body());
            else LOG.info("企微告警已发送");
        }
        catch (Exception e) { LOG.error("企微告警发送异常: {}", e.getMessage()); }
    }

    private String hash(String s)
    {
        try
        {
            MessageDigest md = MessageDigest.getInstance("MD5");
            StringBuilder sb = new StringBuilder();
            for (byte b : md.digest((s != null ? s : "").getBytes(StandardCharsets.UTF_8)))
                sb.append(String.format("%02x", b));
            return sb.substring(0, 8);
        }
        catch (Exception e) { return Integer.toHexString(s != null ? s.hashCode() : 0); }
    }

    private String truncate(String s, int max)
    { return s == null ? "" : s.length() <= max ? s : s.substring(0, max) + "..."; }

    private String resolveName(String code)
    {
        switch (code)
        {
            case "base": return "基础数据同步";
            case "ebay": return "eBay数据同步";
            case "amz": return "AMZ补货数据同步";
            case "fba": return "FBA货件数据同步";
            case "stock_order": return "备货单数据同步";
            case "goodcang": return "谷仓数据同步";
            default: return code;
        }
    }
}
