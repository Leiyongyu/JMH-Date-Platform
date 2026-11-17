package com.ruoyi.system.service.operation.sync;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.MailSendException;
import org.springframework.mail.javamail.JavaMailSenderImpl;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class SyncAlertMailSenderTest
{
    private SyncAlertMailProperties config()
    {
        var config=new SyncAlertMailProperties();
        config.setUsername("sender@example.com"); config.setTo("recipient@example.com");
        config.setPassword("test-only"); return config;
    }

    @Test void secureTransportAndPlainTextContent()
    {
        var config=config();
        var real=new SyncAlertMailSender(config).createSender();
        assertEquals(465,real.getPort());
        assertEquals("true",real.getJavaMailProperties().getProperty("mail.smtp.ssl.enable"));
        assertEquals("true",real.getJavaMailProperties().getProperty("mail.smtp.ssl.checkserveridentity"));
        var transport=mock(JavaMailSenderImpl.class);
        var sender=new SyncAlertMailSender(config) { protected JavaMailSenderImpl createSender() { return transport; } };
        assertTrue(sender.send("## 同步告警\n> 步骤：补货建议\n> 状态：FAILED"));
        var message=ArgumentCaptor.forClass(SimpleMailMessage.class);
        verify(transport).send(message.capture());
        assertEquals("[JMH] 同步告警 步骤：补货建议",message.getValue().getSubject());
        assertEquals("同步告警\n步骤：补货建议\n状态：FAILED",message.getValue().getText());
        assertArrayEquals(new String[]{"recipient@example.com"},message.getValue().getTo());
    }

    @Test void failureAndInvalidConfigurationDoNotDeliver()
    {
        var config=config(); var transport=mock(JavaMailSenderImpl.class);
        var sender=new SyncAlertMailSender(config) { protected JavaMailSenderImpl createSender() { return transport; } };
        doThrow(new MailSendException("test failure")).when(transport).send(any(SimpleMailMessage.class));
        assertFalse(sender.send("test"));
        reset(transport);
        config.setTo("recipient@example.com\r\nBcc: injected@example.com");
        assertFalse(sender.send("test"));
        verifyNoInteractions(transport);
        config.setPassword(""); assertFalse(sender.isConfigured()); assertFalse(sender.send("test"));
        verifyNoInteractions(transport);
    }
}
