package com.ruoyi.system.mapper.operation.external;

import com.ruoyi.system.domain.operation.external.AmzFbaShipment;
import java.time.LocalDate;
import java.util.Collection;
import java.util.Date;
import java.util.List;
import java.util.Map;
import org.apache.ibatis.annotations.Param;

public interface AmzFbaShipmentMapper
{
    List<AmzFbaShipment> selectAll();

    /** 检查表是否为空 */
    int count();

    /** 按唯一键 upsert */
    int insert(AmzFbaShipment row);

    /** 批量插入 */
    int batchInsert(@Param("list") List<AmzFbaShipment> list);

    /** 批量 upsert (INSERT ... ON DUPLICATE KEY UPDATE) */
    int batchUpsert(@Param("list") List<AmzFbaShipment> list);

    /** 增强搜索 */
    List<AmzFbaShipment> search(@Param("params") Map<String, Object> params);

    /** 增强搜索总数 */
    long searchCount(@Param("params") Map<String, Object> params);

    /** 去重 sid + shipment_id（用于装箱信息同步） */
    List<Map<String, Object>> selectDistinctSidShipment();

    /** 去重货件单号（用于查询领星发货单号映射） */
    List<String> selectDistinctShipmentIds();

    /** 已完成货件的 sid + shipment_id，按最近N天筛选 */
    List<Map<String, Object>> selectClosedSidShipmentByDays(@Param("days") int days);

    /** 去重店铺名称 */
    List<String> selectDistinctStoreNames();

    /**
     * 取数据库当前时间作为本次同步的基准时刻。
     * 必须用库时间而不是 Java 的 new Date()：sync_time 写的是 MySQL 的 NOW()，
     * 两者若来自不同主机且库时钟偏慢，本次写入的行会被误判为陈旧行而遭清理。
     */
    Date selectDatabaseNow();

    /** 统计本次同步窗口内、指定店铺下接口已不再返回的陈旧行数，用于清理前的熔断判断 */
    int countStaleBySids(@Param("sids") Collection<Integer> sids,
                         @Param("runStart") Date runStart,
                         @Param("startDate") LocalDate startDate,
                         @Param("endDate") LocalDate endDate);

    /** 删除本次同步窗口内、指定店铺下接口已不再返回的陈旧行（SKU改名遗留的重复行） */
    int deleteStaleBySids(@Param("sids") Collection<Integer> sids,
                          @Param("runStart") Date runStart,
                          @Param("startDate") LocalDate startDate,
                          @Param("endDate") LocalDate endDate);
}
