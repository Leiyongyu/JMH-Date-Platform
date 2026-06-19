package com.ruoyi.system.service.operation;

import com.ruoyi.system.service.operation.sync.OperationSyncResult;

/**
 * 业务同步日志服务 —— 统一管理 data_sync_log 的写入。
 *
 * @author JMH
 */
public interface IOperationSyncLogService
{
    /**
     * 开始一次同步：写入 RUNNING 状态记录，返回日志 ID 供后续更新。
     */
    Long start(String syncType, String syncName, String apiPath,
               String triggerType, String operator, Long jobId, Long jobLogId);

    /**
     * 开始一次同步（支持父子日志关联）。
     * @param parentId 父日志 ID（子步骤用），顶级调用传 null
     */
    Long start(String syncType, String syncName, String apiPath,
               String triggerType, String operator, Long jobId, Long jobLogId, Long parentId);

    /**
     * 完成一次同步：根据结果更新日志状态和统计信息。
     *
     * @param logId  日志记录 ID
     * @param result 同步结果
     */
    void finish(Long logId, OperationSyncResult result);

    /**
     * 查询单条日志。
     */
    com.ruoyi.system.domain.operation.DataSyncLog getById(Long id);

    /**
     * 清理 N 天前的日志。
     */
    int cleanOldLogs(int days);
}
