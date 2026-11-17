package com.ruoyi.web.task;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class OperationSyncTaskTimeoutTest
{
    @Test void onlyRestockGetsLongerTimeoutAndLockOutlivesItsDeadline()
    {
        assertEquals(90,OperationSyncTask.timeoutMinutes("amz_restock_summary"));
        assertEquals(6300,OperationSyncTask.lockTimeoutSeconds("amz_restock_summary"));
        for (String type:new String[]{"amz_product_inventory","amz_order_profit","warehouse"})
        {
            assertEquals(30,OperationSyncTask.timeoutMinutes(type));
            assertEquals(2700,OperationSyncTask.lockTimeoutSeconds(type));
        }
    }
}
