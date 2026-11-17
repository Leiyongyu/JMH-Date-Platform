package com.ruoyi.system.service.operation.sync;

import com.ruoyi.common.core.redis.RedisCache;
import com.ruoyi.common.utils.spring.SpringUtils;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class SyncAlertServiceMailTest
{
    @Test void failedMailReleasesDedupAndMissingConfigurationDoesNotSend()
    {
        var sender=mock(SyncAlertMailSender.class); var redis=mock(RedisCache.class);
        var service=new SyncAlertService(sender);
        ReflectionTestUtils.setField(service,"enabled",true);
        when(sender.isConfigured()).thenReturn(true);
        when(redis.setCacheObjectIfAbsent(anyString(),eq("1"),eq(60),eq(TimeUnit.MINUTES))).thenReturn(true);
        try (var spring=mockStatic(SpringUtils.class))
        {
            spring.when(() -> SpringUtils.getBean(RedisCache.class)).thenReturn(redis);
            service.sendAlert("amz","restock","FAILED","pagination changed",215L);
            verify(sender).send(contains("pagination changed"));
            verify(redis).deleteObject(startsWith("alert:sent:amz:restock:"));
            reset(sender,redis);
            service.sendAlert("amz","restock","FAILED","test",215L);
            verify(sender,never()).send(anyString());
            verifyNoInteractions(redis);
        }
    }

    @Test void successfulMailKeepsDedupAndCredentialFailureAllowsRetry()
    {
        var sender=mock(SyncAlertMailSender.class); var redis=mock(RedisCache.class);
        var service=new SyncAlertService(sender);
        ReflectionTestUtils.setField(service,"enabled",true);
        when(sender.isConfigured()).thenReturn(true);
        when(sender.send(anyString())).thenReturn(true);
        when(redis.setCacheObjectIfAbsent(anyString(),eq("1"),anyInt(),any())).thenReturn(true);
        try (var spring=mockStatic(SpringUtils.class))
        {
            spring.when(() -> SpringUtils.getBean(RedisCache.class)).thenReturn(redis);
            service.sendAlert("quartz","job:215","FAILED","test",215L);
            verify(redis,never()).deleteObject(anyString());
            when(sender.send(anyString())).thenReturn(false);
            assertFalse(service.sendCredentialReminder("test-event","test reminder"));
            verify(redis).deleteObject(startsWith("alert:sent:ebay-credential:"));
        }
    }
}
