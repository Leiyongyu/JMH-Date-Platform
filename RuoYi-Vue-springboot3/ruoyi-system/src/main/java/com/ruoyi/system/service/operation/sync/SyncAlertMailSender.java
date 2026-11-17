package com.ruoyi.system.service.operation.sync;

import jakarta.mail.internet.InternetAddress;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSenderImpl;
import org.springframework.stereotype.Service;

/** SMTP only: a delivery failure never falls back to a group webhook. */
@Service
public class SyncAlertMailSender
{
    private static final Logger LOG = LoggerFactory.getLogger(SyncAlertMailSender.class);
    private final SyncAlertMailProperties config;
    public SyncAlertMailSender(SyncAlertMailProperties config) { this.config = config; }

    public boolean isConfigured()
    {
        return config.getHost() != null && !config.getHost().isBlank()
                && config.getUsername() != null && !config.getUsername().isBlank()
                && config.getPassword() != null && !config.getPassword().isBlank()
                && config.getTo() != null && !config.getTo().isBlank();
    }

    protected JavaMailSenderImpl createSender()
    {
        var sender = new JavaMailSenderImpl();
        sender.setHost(config.getHost()); sender.setPort(config.getPort());
        sender.setUsername(config.getUsername()); sender.setPassword(config.getPassword());
        sender.setDefaultEncoding("UTF-8");
        var properties = sender.getJavaMailProperties();
        properties.setProperty("mail.smtp.auth", "true");
        properties.setProperty("mail.smtp.ssl.enable", String.valueOf(config.isSsl()));
        properties.setProperty("mail.smtp.ssl.checkserveridentity", "true");
        properties.setProperty("mail.smtp.starttls.enable", String.valueOf(!config.isSsl()));
        properties.setProperty("mail.smtp.starttls.required", String.valueOf(!config.isSsl()));
        properties.setProperty("mail.smtp.connectiontimeout", "10000");
        properties.setProperty("mail.smtp.timeout", "15000");
        properties.setProperty("mail.smtp.writetimeout", "15000");
        return sender;
    }

    public boolean send(String content)
    {
        if (!isConfigured()) { LOG.warn("告警邮件未发送：缺少SMTP账号、授权码或收件地址"); return false; }
        try
        {
            String from = address(config.getUsername());
            String to = address(config.getTo());
            String body = content == null ? "" : content.replaceAll("(?m)^##\\s*", "").replaceAll("(?m)^>\\s*", "");
            String heading = body.lines().findFirst().orElse("任务通知");
            String task = body.lines().filter(line -> line.startsWith("步骤：") || line.startsWith("任务："))
                    .findFirst().orElse("");
            String subject = ("[JMH] " + heading + " " + task).replaceAll("[\\r\\n]", " ");
            var message = new SimpleMailMessage();
            message.setFrom(from); message.setTo(to);
            message.setSubject(subject.substring(0, Math.min(180, subject.length())));
            message.setText(body);
            createSender().send(message);
            LOG.info("任务通知邮件已交给SMTP服务器");
            return true;
        }
        catch (Exception ex)
        {
            LOG.error("任务通知邮件发送失败：{}；请检查SMTP配置。未转发企微群。", ex.getClass().getSimpleName());
            return false;
        }
    }

    private static String address(String value) throws Exception
    {
        if (value.indexOf('\r') >= 0 || value.indexOf('\n') >= 0) throw new IllegalArgumentException("invalid address");
        var address = new InternetAddress(value.trim(), true);
        address.validate();
        return address.getAddress();
    }
}
