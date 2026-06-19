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
     *
     * @param syncType    同步类型标识
     * @param syncName    同步名称（中文）
     * @param apiPath     API 路径
     * @param triggerType 触发方式 MANUAL / JOB
     * @param operator    操作人
     * @param jobId       若依任务 ID（可为 null）
     * @param jobLogId    若依任务日志 ID（可为 null）
     * @return 日志记录 ID
     */
    Long start(String syncType, String syncName, String apiPath,
               String triggerType, String operator, Long jobId, Long jobLogId);

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
