package com.ruoyi.system.service.operation.impl;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.system.domain.operation.DataSyncLog;
import com.ruoyi.system.mapper.operation.DataSyncLogMapper;
import com.ruoyi.system.service.operation.IOperationSyncLogService;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import java.time.LocalDateTime;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class OperationSyncLogServiceImpl implements IOperationSyncLogService
{
    private static final Logger LOG = LoggerFactory.getLogger(OperationSyncLogServiceImpl.class);

    private final DataSyncLogMapper mapper;
    private final ObjectMapper objectMapper;

    public OperationSyncLogServiceImpl(DataSyncLogMapper mapper, ObjectMapper objectMapper)
    {
        this.mapper = mapper;
        this.objectMapper = objectMapper;
    }

    @Override
    public Long start(String syncType, String syncName, String apiPath,
                      String triggerType, String operator, Long jobId, Long jobLogId)
    {
        return start(syncType, syncName, apiPath, triggerType, operator, jobId, jobLogId, null);
    }

    @Override
    public Long start(String syncType, String syncName, String apiPath,
                      String triggerType, String operator, Long jobId, Long jobLogId, Long parentId)
    {
        DataSyncLog log = new DataSyncLog();
        log.setSyncType(syncType);
        log.setSyncName(syncName);
        log.setApiPath(apiPath);
        log.setStatus(OperationSyncResult.STATUS_RUNNING);
        log.setTriggerType(triggerType != null ? triggerType : "JOB");
        log.setOperator(operator != null ? operator : "SYSTEM");
        log.setJobId(jobId);
        log.setJobLogId(jobLogId);
        log.setParentId(parentId);
        log.setStartTime(LocalDateTime.now());
        log.setTotalCount(0);
        log.setSuccessCount(0);
        log.setFailCount(0);
        mapper.insert(log);
        return log.getId();
    }

    @Override
    public void finish(Long logId, OperationSyncResult result)
    {
        if (logId == null || result == null) return;

        DataSyncLog log = new DataSyncLog();
        log.setId(logId);
        log.setStatus(result.getStatus());
        log.setEndTime(LocalDateTime.now());
        log.setTotalCount(result.getTotalCount());
        log.setSuccessCount(result.getSuccessCount());
        log.setFailCount(result.getFailCount());
        log.setErrorMessage(truncate(result.getErrorMessage(), 2000));

        try
        {
            log.setDetailJson(objectMapper.writeValueAsString(result));
            if (result.getFailures() != null && !result.getFailures().isEmpty())
            {
                log.setFailedJson(objectMapper.writeValueAsString(result.getFailures()));
            }
        }
        catch (JsonProcessingException e)
        {
            LOG.warn("Serialize sync result json failed: {}", e.getMessage());
        }

        mapper.updateById(log);
    }

    @Override
    public DataSyncLog getById(Long id)
    {
        return mapper.selectById(id);
    }

    @Override
    public int cleanOldLogs(int days)
    {
        return mapper.deleteOlderThan(days);
    }

    @Override
    public List<DataSyncLog> getChildren(Long parentId)
    {
        return mapper.selectByParentId(parentId);
    }

    @Override
    public List<DataSyncLog> search(String syncType, String status, String triggerType)
    {
        return mapper.search(syncType, status, triggerType);
    }

    private String truncate(String text, int maxLen)
    {
        if (text == null) return null;
        return text.length() <= maxLen ? text : text.substring(0, maxLen);
    }
}
