package com.ruoyi.system.mapper.operation;

import java.util.List;
import org.apache.ibatis.annotations.Param;
import com.ruoyi.system.domain.operation.DataSyncLog;

/**
 * 业务数据同步日志 Mapper。
 */
public interface DataSyncLogMapper
{
    int insert(DataSyncLog log);
    int updateById(DataSyncLog log);
    DataSyncLog selectById(Long id);
    int deleteOlderThan(int days);
    List<DataSyncLog> selectByParentId(@Param("parentId") Long parentId);
    List<DataSyncLog> search(@Param("syncType") String syncType, @Param("status") String status, @Param("triggerType") String triggerType);
}
