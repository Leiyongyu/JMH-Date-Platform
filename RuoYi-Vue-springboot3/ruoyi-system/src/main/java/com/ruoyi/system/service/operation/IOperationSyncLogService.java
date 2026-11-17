package com.ruoyi.system.service.operation;

import com.ruoyi.system.domain.operation.DataSyncLog;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import java.util.List;

/**
 * 业务同步日志服务 —— 统一管理 data_sync_log 的写入和查询。
 */
public interface IOperationSyncLogService
{
    Long start(String syncType, String syncName, String apiPath,
               String triggerType, String operator, Long jobId, Long jobLogId);
    Long start(String syncType, String syncName, String apiPath,
               String triggerType, String operator, Long jobId, Long jobLogId, Long parentId);
    void finish(Long logId, OperationSyncResult result);
    DataSyncLog getById(Long id);
    /** 查询子步骤 */
    List<DataSyncLog> getChildren(Long parentId);
    /** 分页搜索 */
    List<DataSyncLog> search(String syncType, String status, String triggerType);
    int cleanOldLogs(int days);
}
