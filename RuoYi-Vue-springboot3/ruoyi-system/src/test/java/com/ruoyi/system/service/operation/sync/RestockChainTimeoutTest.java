package com.ruoyi.system.service.operation.sync;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class RestockChainTimeoutTest
{
    @Test void restockRetriesFitInsideLocksAndOtherStepTimeoutsStayUnchanged()
    {
        assertEquals(90,SyncOrchestratorService.stepTimeoutMinutes("amz_restock"));
        assertTrue(SyncOrchestratorService.stepLockSeconds("amz_restock") > 2*90*60);
        assertTrue(SyncOrchestratorService.chainLockSeconds(SyncOrchestratorService.Chain.AMZ)
                > SyncOrchestratorService.stepLockSeconds("amz_restock"));
        assertEquals(60,SyncOrchestratorService.stepTimeoutMinutes("amz_listing"));
        assertEquals(3600,SyncOrchestratorService.stepLockSeconds("amz_listing"));
        assertEquals(4500,SyncOrchestratorService.chainLockSeconds(SyncOrchestratorService.Chain.EBAY));
    }
}
