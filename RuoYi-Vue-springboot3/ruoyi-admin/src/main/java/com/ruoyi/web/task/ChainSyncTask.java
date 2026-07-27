package com.ruoyi.web.task;

import com.ruoyi.common.utils.spring.SpringUtils;
import com.ruoyi.system.service.operation.sync.SyncOrchestratorService;
import org.springframework.stereotype.Component;

/**
 * 同步链路 Quartz 入口。每条链路委托给 {@link SyncOrchestratorService} 执行。
 */
@Component("chainSyncTask")
public class ChainSyncTask
{
    public void runBaseChain()       { SpringUtils.getBean(SyncOrchestratorService.class).execute("base"); }
    public void runEbayChain()       { SpringUtils.getBean(SyncOrchestratorService.class).execute("ebay"); }
    public void runAmzChain()        { SpringUtils.getBean(SyncOrchestratorService.class).execute("amz"); }
    public void runFbaChain()        { SpringUtils.getBean(SyncOrchestratorService.class).execute("fba"); }
    public void runStockOrderChain() { SpringUtils.getBean(SyncOrchestratorService.class).execute("stock_order"); }
    public void runStaShipmentChain(){ SpringUtils.getBean(SyncOrchestratorService.class).execute("sta_shipment"); }
    public void runGoodcangChain()   { SpringUtils.getBean(SyncOrchestratorService.class).execute("goodcang"); }
}
