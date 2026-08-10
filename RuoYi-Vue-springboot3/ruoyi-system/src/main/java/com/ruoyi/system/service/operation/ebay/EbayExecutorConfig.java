package com.ruoyi.system.service.operation.ebay;

import java.util.concurrent.ThreadPoolExecutor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

/**
 * eBay 查询使用独立有界线程池，避免占用公共 ForkJoinPool。
 */
@Configuration
public class EbayExecutorConfig
{
    @Bean(name = "ebaySearchExecutor")
    public ThreadPoolTaskExecutor ebaySearchExecutor(EbayProperties properties)
    {
        return executor("ebay-search-", properties.getSearchMaxWorkers(),
                Math.max(50, properties.getSearchMaxKeywords()));
    }

    @Bean(name = "ebayDetailExecutor")
    public ThreadPoolTaskExecutor ebayDetailExecutor(EbayProperties properties)
    {
        return executor("ebay-detail-", properties.getDetailMaxWorkers(), 500);
    }

    @Bean(name = "ebayAuditExecutor")
    public ThreadPoolTaskExecutor ebayAuditExecutor(EbayProperties properties)
    {
        return executor("ebay-audit-", properties.getAuditMaxConcurrentTasks(), 30);
    }

    private ThreadPoolTaskExecutor executor(String prefix, int workerCount, int queueCapacity)
    {
        int workers = Math.max(1, workerCount);
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setThreadNamePrefix(prefix);
        executor.setCorePoolSize(workers);
        executor.setMaxPoolSize(workers);
        executor.setQueueCapacity(Math.max(1, queueCapacity));
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(15);
        executor.setRejectedExecutionHandler(new ThreadPoolExecutor.CallerRunsPolicy());
        executor.initialize();
        return executor;
    }
}
