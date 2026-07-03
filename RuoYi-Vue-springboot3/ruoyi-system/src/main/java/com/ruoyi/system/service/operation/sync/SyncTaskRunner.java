package com.ruoyi.system.service.operation.sync;

import com.ruoyi.common.utils.spring.SpringUtils;
import com.ruoyi.system.domain.operation.TaskStatus;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Component;

/**
 * Separated bean so that {@code @Async} works through the Spring proxy.
 * <p>
 * <b>Do NOT call these methods from within this class</b> — self-invocation
 * bypasses the AOP proxy and the call runs synchronously.
 * Always call through the injected {@code SyncTaskRunner} bean reference.
 */
@Component
public class SyncTaskRunner
{
    private static final Logger LOG = LoggerFactory.getLogger(SyncTaskRunner.class);

    @Async("syncTaskExecutor")
    public void runEbay(SyncTaskAsyncService.SyncSubmission sub, String triggerType, String operator, String scope)
    {
        sub.markRunning();
        LOG.info("eBay async sync started: submissionId={}, scope={}", sub.submissionId, scope);
        try
        {
            EbayUnifiedSyncService svc = SpringUtils.getBean(EbayUnifiedSyncService.class);
            Map<String, Object> result = "refresh".equals(scope)
                    ? svc.refreshOnly(triggerType, operator)
                    : svc.syncAll(triggerType, operator);
            sub.completeFrom(result);
        }
        catch (Exception e)
        {
            LOG.error("eBay async sync failed: submissionId={}, error={}", sub.submissionId, e.getMessage(), e);
            sub.markFailed(e.getMessage());
        }
    }

    @Async("syncTaskExecutor")
    public void runAmz(SyncTaskAsyncService.SyncSubmission sub, String triggerType, String operator, String scope)
    {
        sub.markRunning();
        LOG.info("AMZ async sync started: submissionId={}, scope={}", sub.submissionId, scope);
        try
        {
            AmzUnifiedSyncService svc = SpringUtils.getBean(AmzUnifiedSyncService.class);
            Map<String, Object> result = "refresh".equals(scope)
                    ? svc.refreshOnly(triggerType, operator)
                    : svc.syncAll(triggerType, operator);
            sub.completeFrom(result);
        }
        catch (Exception e)
        {
            LOG.error("AMZ async sync failed: submissionId={}, error={}", sub.submissionId, e.getMessage(), e);
            sub.markFailed(e.getMessage());
        }
    }

    @Async("syncTaskExecutor")
    public void runStockOrder(SyncTaskAsyncService.SyncSubmission sub, String operator)
    {
        sub.markRunning();
        LOG.info("Stock-order async sync started: submissionId={}", sub.submissionId);
        try
        {
            OperationSyncResult r = SpringUtils.getBean(
                    com.ruoyi.system.service.operation.external.lingxing.OverseasStockOrderSyncService.class)
                    .sync();
            if (TaskStatus.SUCCESS.getValue().equals(r.getStatus()))
                sub.markSuccess("SUCCESS");
            else
                sub.markFailed(r.getErrorMessage());
        }
        catch (Exception e)
        {
            LOG.error("Stock-order async sync failed: submissionId={}, error={}", sub.submissionId, e.getMessage(), e);
            sub.markFailed(e.getMessage());
        }
    }
}
