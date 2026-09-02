package com.ruoyi.system.service.operation.customs;

import java.util.concurrent.Executor;
import java.util.concurrent.ThreadPoolExecutor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

/** 为报关长耗时导入提供隔离线程池，队列满时明确拒绝，禁止回退占用HTTP线程。 */
@Configuration
public class CustomsImportExecutorConfig
{
    @Bean(name = "customsImportTaskExecutor")
    public Executor customsImportTaskExecutor()
    {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(20);
        executor.setKeepAliveSeconds(120);
        executor.setThreadNamePrefix("customs-import-");
        executor.setRejectedExecutionHandler(new ThreadPoolExecutor.AbortPolicy());
        executor.initialize();
        return executor;
    }
}
