package com.ruoyi.system.service.operation.ebay;

import com.ruoyi.common.exception.ServiceException;
import com.ruoyi.system.domain.operation.ebay.EbayWarehouseRentDetail;
import com.ruoyi.system.domain.operation.ebay.EbayWarehouseProductKey;
import com.ruoyi.system.mapper.operation.ebay.EbayWarehouseRentDetailMapper;
import com.ruoyi.system.mapper.operation.ebay.EbayWarehouseRentMapper;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.concurrent.locks.ReentrantLock;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;

/** 仓租明细按仓库、商品编码与账单日增量覆盖，并从全量明细重建仓租汇总。 */
@Service
public class EbayWarehouseRentReplaceService
{
    private static final int BATCH_SIZE = 500;
    private static final ReentrantLock IMPORT_LOCK = new ReentrantLock();

    private final EbayWarehouseRentDetailMapper detailMapper;
    private final EbayWarehouseRentMapper aggregateMapper;
    private final TransactionTemplate transactionTemplate;

    public EbayWarehouseRentReplaceService(
            EbayWarehouseRentDetailMapper detailMapper,
            EbayWarehouseRentMapper aggregateMapper,
            PlatformTransactionManager transactionManager)
    {
        this.detailMapper = detailMapper;
        this.aggregateMapper = aggregateMapper;
        this.transactionTemplate = new TransactionTemplate(transactionManager);
        this.transactionTemplate.setPropagationBehavior(
                TransactionDefinition.PROPAGATION_REQUIRES_NEW);
    }

    /**
     * JVM锁快速拒绝同实例重复导入，数据库控制行锁负责多实例串行。
     * TransactionTemplate返回时事务已提交，所以JVM锁不会在提交前释放。
     */
    public ReplaceResult replace(List<EbayWarehouseRentDetail> items)
    {
        if (items == null || items.isEmpty())
        {
            throw new ServiceException("仓租明细没有可覆盖的数据");
        }
        Set<EbayWarehouseProductKey> distinctKeys = new LinkedHashSet<>();
        for (EbayWarehouseRentDetail item : items)
        {
            if (item == null
                    || item.getWarehouseCode() == null
                    || item.getWarehouseCode().isBlank()
                    || item.getProductCode() == null
                    || item.getProductCode().isBlank()
                    || item.getBillingTimeText() == null
                    || item.getBillingTimeText().isBlank())
            {
                throw new ServiceException(
                        "仓租明细存在空仓库、空商品编码或空计费时间，已拒绝覆盖");
            }
            distinctKeys.add(new EbayWarehouseProductKey(
                    item.getWarehouseCode().trim(),
                    item.getProductCode().trim(),
                    item.getBillingTimeText().trim()));
        }
        List<EbayWarehouseProductKey> keys = List.copyOf(distinctKeys);

        if (!IMPORT_LOCK.tryLock())
        {
            throw new ServiceException("另一位用户正在上传仓租明细，请稍后再试");
        }
        try
        {
            ReplaceResult result = transactionTemplate.execute(status ->
                    replaceInTransaction(items, keys));
            if (result == null)
                throw new ServiceException("仓租明细覆盖事务未返回结果");
            return result;
        }
        finally
        {
            IMPORT_LOCK.unlock();
        }
    }

    private ReplaceResult replaceInTransaction(
            List<EbayWarehouseRentDetail> items,
            List<EbayWarehouseProductKey> keys)
    {
        String lockKey = detailMapper.lockImport();
        if (lockKey == null)
        {
            throw new ServiceException(
                    "仓租导入控制锁未初始化，请先执行数据库部署脚本");
        }

        for (int start = 0; start < keys.size(); start += BATCH_SIZE)
        {
            int end = Math.min(start + BATCH_SIZE, keys.size());
            detailMapper.deleteByWarehouseProductBillingDays(
                    keys.subList(start, end));
        }

        int inserted = 0;
        for (int start = 0; start < items.size(); start += BATCH_SIZE)
        {
            int end = Math.min(start + BATCH_SIZE, items.size());
            inserted += detailMapper.batchInsert(items.subList(start, end));
        }
        if (inserted != items.size())
        {
            throw new ServiceException(
                    "仓租明细覆盖不完整，期望写入" + items.size()
                    + "条，实际写入" + inserted + "条");
        }

        EbayWarehouseRentDetail metadata = items.get(0);
        aggregateMapper.deleteAll();
        int aggregateRows = aggregateMapper.rebuildFromDetails(
                metadata.getImportBatchId(),
                metadata.getSourceFileName(),
                metadata.getImportedBy());
        if (aggregateRows <= 0)
        {
            throw new ServiceException("仓租明细已写入，但汇总表重建结果为空");
        }
        return new ReplaceResult(
                inserted, keys.size(), aggregateRows);
    }

    public record ReplaceResult(
            int detailRowCount,
            int replacedWarehouseProductBillingDayCount,
            int aggregateRowCount)
    {
    }
}
