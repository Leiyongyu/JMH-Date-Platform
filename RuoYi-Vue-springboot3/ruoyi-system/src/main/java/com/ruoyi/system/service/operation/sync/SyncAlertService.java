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
import java.util.concurrent.TimeUnit;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
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

    private static final String ALERT_PREFIX = "alert:sent:";
    private static final int DEDUP_MINUTES = 60;
    private static final HttpClient HTTP = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(10)).build();
    private static final DateTimeFormatter DTF = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");

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

        markFailed(chainCode, stepCode);
        String dedupKey = ALERT_PREFIX + chainCode + ":" + stepCode + ":" + hash(error);
        RedisCache redis = SpringUtils.getBean(RedisCache.class);
        if (!redis.setCacheObjectIfAbsent(dedupKey, "1", DEDUP_MINUTES, TimeUnit.MINUTES))
        { LOG.debug("告警已去重 {}", dedupKey); return; }

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
