package com.ruoyi.system.mapper.operation;

import java.util.List;
import org.apache.ibatis.annotations.Param;
import com.ruoyi.system.domain.operation.ebay.EbayPriceAuditItem;
import com.ruoyi.system.domain.operation.ebay.EbayPriceAuditOe;
import com.ruoyi.system.domain.operation.ebay.EbayPriceAuditTask;

/** eBay 价格批量审核任务数据访问。 */
public interface EbayPriceAuditMapper
{
    int insertTask(EbayPriceAuditTask task);

    int batchInsertOes(@Param("rows") List<EbayPriceAuditOe> rows);

    EbayPriceAuditTask selectTask(@Param("taskId") Long taskId, @Param("userId") Long userId);

    EbayPriceAuditTask selectLatestTask(@Param("userId") Long userId);

    List<EbayPriceAuditTask> selectRecentTasks(@Param("userId") Long userId);

    List<EbayPriceAuditTask> selectQueryingTasks();

    List<EbayPriceAuditOe> selectOes(@Param("taskId") Long taskId);

    EbayPriceAuditOe selectOe(@Param("taskId") Long taskId, @Param("oeId") Long oeId);

    List<EbayPriceAuditItem> selectItems(@Param("taskId") Long taskId, @Param("oeId") Long oeId);

    List<EbayPriceAuditItem> selectSelectedItems(@Param("taskId") Long taskId);

    int countQueryingTasks();

    int markOeQuerying(@Param("oeId") Long oeId);

    int deleteItemsByOe(@Param("oeId") Long oeId);

    int deleteItemsByTask(@Param("taskId") Long taskId);

    int deleteOesByTask(@Param("taskId") Long taskId);

    int deleteTask(@Param("taskId") Long taskId, @Param("userId") Long userId);

    int batchInsertItems(@Param("rows") List<EbayPriceAuditItem> rows);

    int markOeFinished(@Param("oeId") Long oeId, @Param("queryStatus") String queryStatus,
            @Param("reviewStatus") String reviewStatus, @Param("resultCount") int resultCount,
            @Param("errorMessage") String errorMessage);

    int clearSelectedItems(@Param("oeId") Long oeId);

    int selectReviewedItems(@Param("oeId") Long oeId, @Param("itemIds") List<Long> itemIds);

    int markOeReviewed(@Param("oeId") Long oeId, @Param("reviewStatus") String reviewStatus,
            @Param("selectedCount") int selectedCount, @Param("reviewBy") String reviewBy);

    int refreshTaskStats(@Param("taskId") Long taskId);
}
