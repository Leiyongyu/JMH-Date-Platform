package com.ruoyi.system.service.operation.sync;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Properties;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** Explicit opt-in only: sends exactly one clearly labelled test message. */
@EnabledIfEnvironmentVariable(named="SYNC_ALERT_LIVE_TEST", matches="1")
class SyncAlertMailLiveTest
{
    @Test void sendOneTestEmailUsingPrivateServerConfiguration() throws Exception
    {
        var properties=new Properties();
        var path=Path.of(System.getProperty("user.home"),".jmh-platform","alert-mail.properties");
        try (var input=Files.newBufferedReader(path)) { properties.load(input); }
        var config=new SyncAlertMailProperties();
        config.setHost(properties.getProperty("sync.alert.mail.host"));
        config.setPort(Integer.parseInt(properties.getProperty("sync.alert.mail.port")));
        config.setSsl(Boolean.parseBoolean(properties.getProperty("sync.alert.mail.ssl")));
        config.setUsername(properties.getProperty("sync.alert.mail.username"));
        config.setPassword(properties.getProperty("sync.alert.mail.password"));
        config.setTo(properties.getProperty("sync.alert.mail.to"));
        assertTrue(new SyncAlertMailSender(config).send("## 邮件告警通道测试\n"
                + "> 任务：JMH SMTP连接验证\n> 这是一次人工配置测试，不代表同步任务失败。\n"
                + "> 本邮件由本地Java告警发送器发出，未执行数据同步或修改业务数据。"),
                "SMTP test was not accepted; inspect sanitized transport status");
    }
}
