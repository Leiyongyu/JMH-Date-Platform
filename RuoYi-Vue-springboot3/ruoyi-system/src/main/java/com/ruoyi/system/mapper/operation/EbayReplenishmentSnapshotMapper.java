package com.ruoyi.system.mapper.operation;

import java.util.List;
import java.util.Map;

import org.apache.ibatis.annotations.Param;

import com.ruoyi.system.domain.operation.EbayReplenishmentSnapshot;

public interface EbayReplenishmentSnapshotMapper
{
    /** 基础查询（若依兼容） */
    List<EbayReplenishmentSnapshot> selectEbayReplenishmentSnapshotList(EbayReplenishmentSnapshot snapshot);

    /** 新版搜索：全部筛选下推 SQL */
    List<EbayReplenishmentSnapshot> search(Map<String, Object> params);

    /** 候选值 distinct 查询 */
    List<String> selectDistinctValues(@Param("column") String column, @Param("keyword") String keyword);

    /** 单条插入 */
    int insertSnapshot(EbayReplenishmentSnapshot snapshot);

    /** 批量插入 */
    int batchInsertSnapshots(List<EbayReplenishmentSnapshot> list);

    /** 清空表 */
    int deleteAll();
}
