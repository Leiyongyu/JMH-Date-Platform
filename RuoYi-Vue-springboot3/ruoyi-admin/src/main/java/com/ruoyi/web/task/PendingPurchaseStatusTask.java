package com.ruoyi.web.task;

import com.ruoyi.system.service.procurement.PendingPurchaseStatusService;
import com.ruoyi.system.service.operation.sync.OperationSyncContext;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Component;

@Component("pendingPurchaseStatusTask")
public class PendingPurchaseStatusTask
{
    private final PendingPurchaseStatusService service;
    public PendingPurchaseStatusTask(PendingPurchaseStatusService service) { this.service = service; }

    public void sync() { service.sync("JOB", "SYSTEM"); }

    @Async("syncTaskExecutor")
    public void manual(String operator)
    {
        try { service.sync("MANUAL", operator); }
        finally { OperationSyncContext.clear(); }
    }
}
