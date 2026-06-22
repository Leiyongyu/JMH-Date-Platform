package com.ruoyi.system.service.operation.compute;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import com.ruoyi.system.mapper.operation.AmzReplenishmentSnapshotMapper;

/**
 * AMZ补货计算引擎 —— 使用 INSERT...SELECT SQL 一次性聚合。
 * 从旧项目 AmazonComputeService.refreshSnapshot() + AmzInventoryOverviewMapper.insertByListing() 移植。
 *
 * 计算公式（SQL 内完成）：
 *   weightedDailySales = avg_sales_14d*0.5 + avg_sales_30d*0.4 + avg_sales_60d*0.1
 *   avg_monthly_sales  = ROUND(weightedDailySales * 30, 2)
 *   safety_stock       = ROUND(weightedDailySales * 90, 2)
 *   ship_qty           = ROUND(weightedDailySales * 90, 2) - (fba_stock + fba_inbound)
 *   replenish_qty      = ROUND(weightedDailySales * 120, 2) - purchased_qty - domestic_stock - (fba_stock + fba_inbound) - pending_ship
 *   restock_days       = ROUND((total_inventory - replenish_qty) / NULLIF(weightedDailySales, 0), 2)
 *   total_inventory    = fba_sellable + fba_inbound
 */
@Service
public class AmzReplenishmentComputeService
{
    private static final Logger log = LoggerFactory.getLogger(AmzReplenishmentComputeService.class);

    private final AmzReplenishmentSnapshotMapper snapshotMapper;

    public AmzReplenishmentComputeService(AmzReplenishmentSnapshotMapper snapshotMapper)
    {
        this.snapshotMapper = snapshotMapper;
    }

    /**
     * 执行 INSERT...SELECT 生成快照。
     * 由调用方在事务内先 deleteAll() 再调用此方法 + batch 写入。
     */
    public void computeBySql()
    {
        log.info("==== AMZ补货快照 INSERT...SELECT 开始 ====");
        long start = System.currentTimeMillis();
        String batchNo = "AMZ_REPL-" + System.currentTimeMillis();
        int rows = snapshotMapper.insertByListing(batchNo);
        if (rows > 0)
        {
            snapshotMapper.activateBatch(batchNo);
        }
        log.info("==== AMZ补货快照 INSERT...SELECT 完成: {} 条 耗时{}ms ====", rows, System.currentTimeMillis() - start);
    }
}
