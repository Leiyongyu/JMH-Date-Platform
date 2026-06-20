package com.ruoyi.system.service.operation;

import java.util.List;

import com.ruoyi.system.domain.operation.EbayReplenishmentSearchRequest;
import com.ruoyi.system.domain.operation.EbayReplenishmentSnapshot;

public interface IEbayReplenishmentSnapshotService
{
    /** 基础列表查询（若依兼容） */
    List<EbayReplenishmentSnapshot> selectEbayReplenishmentSnapshotList(EbayReplenishmentSnapshot snapshot);

    /**
     * 新版搜索：多字段文本/数值筛选全部下推 SQL，不再内存过滤。
     * 调用方用 PageHelper.startPage() 分页。
     */
    List<EbayReplenishmentSnapshot> search(EbayReplenishmentSearchRequest req);

    /** SQL 级 distinct 候选值（limit 50） */
    List<String> distinctValues(String field, String keyword);

    /** 全量重算并批量写入快照表 */
    int refreshSnapshot();
}
