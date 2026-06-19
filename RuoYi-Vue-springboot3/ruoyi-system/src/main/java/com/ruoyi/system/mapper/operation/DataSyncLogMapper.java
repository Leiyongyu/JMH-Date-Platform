package com.ruoyi.system.mapper.operation;

import com.ruoyi.system.domain.operation.DataSyncLog;

/**
 * 业务数据同步日志 Mapper。
 *
 * @author JMH
 */
public interface DataSyncLogMapper
{
    int insert(DataSyncLog log);

    int updateById(DataSyncLog log);

    DataSyncLog selectById(Long id);

    int deleteOlderThan(int days);
}
