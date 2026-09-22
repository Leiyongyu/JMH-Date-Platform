package com.ruoyi.web.task;

import com.ruoyi.system.service.finance.PythonPerformanceSchedulerClient;
import com.ruoyi.system.service.operation.sync.SyncAlertService;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/** Daily metadata check, independent of monthly listing sync and its failures. */
@Component
public class EbayCredentialReminderService
{
    private static final Logger LOG = LoggerFactory.getLogger(EbayCredentialReminderService.class);
    private final PythonPerformanceSchedulerClient client;
    private final SyncAlertService alerts;
    @Value("${ebay.credentials.reminder.enabled:true}")
    private boolean enabled;

    public EbayCredentialReminderService(PythonPerformanceSchedulerClient client, SyncAlertService alerts)
    {
        this.client = client;
        this.alerts = alerts;
    }

    @Scheduled(cron = "0 0 9 * * *", zone = "Asia/Shanghai")
    public void checkDaily()
    {
        if (!enabled) return;
        try
        {
            Map<String, Object> response = client.ebayCredentialExpiry("ebay-credential-" + UUID.randomUUID());
            if (!(response.get("data") instanceof Map<?, ?> data)
                    || !(data.get("accounts") instanceof List<?> accounts) || accounts.isEmpty())
                throw new IllegalStateException("Invalid credential metadata");
            Map<String, List<Map<?, ?>>> groups = new LinkedHashMap<>();
            for (Object value : accounts)
            {
                if (!(value instanceof Map<?, ?> item)) throw new IllegalStateException("Invalid account metadata");
                String status = String.valueOf(item.get("status"));
                if ("VALID".equals(status)) continue;
                if (!List.of("UNKNOWN_EXPIRY", "EXPIRED", "EXPIRING").contains(status))
                    throw new IllegalStateException("Invalid credential state");
                String key = status + ":" + item.get("expires_on");
                groups.computeIfAbsent(key, ignored -> new ArrayList<>()).add(item);
            }
            // Missing-token rows are intentionally ignored at user's request.
            for (var entry : groups.entrySet())
            {
                List<Map<?, ?>> items = entry.getValue();
                Map<?, ?> first = items.get(0);
                String status = String.valueOf(first.get("status"));
                StringBuilder text = new StringBuilder("## eBay店铺授权密钥更新提醒\n");
                text.append("店铺数：").append(items.size()).append("\n");
                if ("UNKNOWN_EXPIRY".equals(status))
                    text.append("尚未配置授权或到期日期，无法提前一个月提醒。请补充真实日期。\n");
                else
                    text.append("预计到期日期：").append(first.get("expires_on")).append("\n")
                        .append("EXPIRED".equals(status) ? "已到期，请尽快更新授权。\n" : "已进入到期前一个月，请重新授权并更新Excel中的秘钥。\n");
                for (int i = 0; i < Math.min(items.size(), 8); i++)
                {
                    String name = String.valueOf(items.get(i).get("shop_name")).replaceAll("[\\r\\n]", " ");
                    text.append("- ").append(name.substring(0, Math.min(name.length(), 45))).append("\n");
                }
                if (items.size() > 8) text.append("另有").append(items.size() - 8).append("个店铺，请检查紫鸟店铺全量.xlsx。\n");
                text.append("更新密钥后请同步更新到期日期；请勿在群聊发送密钥。");
                if (!alerts.sendCredentialReminder(entry.getKey() + ":" + data.get("checked_on"), text.toString()))
                    throw new IllegalStateException("Reminder not delivered");
            }
        }
        catch (Exception e)
        {
            LOG.warn("eBay凭证提醒检查失败，异常类型={}，未输出敏感正文", e.getClass().getSimpleName());
            alerts.notifyBackgroundFailure("ebay_credential_expiry", "eBay店铺授权有效期检查", "无法完成检查或提醒发送，请检查Python、Redis及企微告警配置");
        }
    }
}
