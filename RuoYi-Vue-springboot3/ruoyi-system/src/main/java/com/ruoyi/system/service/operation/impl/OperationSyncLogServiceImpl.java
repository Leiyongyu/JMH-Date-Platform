package com.ruoyi.system.service.operation.impl;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.system.domain.operation.DataSyncLog;
import com.ruoyi.system.mapper.operation.DataSyncLogMapper;
import com.ruoyi.system.service.operation.IOperationSyncLogService;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;

/**
 * 业务同步日志服务实现。
 *
 * @author JMH
 */
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
        DataSyncLog log = new DataSyncLog();
        log.setSyncType(syncType);
        log.setSyncName(syncName);
        log.setApiPath(apiPath);
        log.setStatus("RUNNING");
        log.setTriggerType(triggerType != null ? triggerType : "JOB");
        log.setOperator(operator != null ? operator : "SYSTEM");
        log.setJobId(jobId);
        log.setJobLogId(jobLogId);
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
        if (logId == null || result == null)
        {
            return;
        }

        DataSyncLog log = new DataSyncLog();
        log.setId(logId);
        log.setStatus(result.getStatus());
        log.setEndTime(LocalDateTime.now());
        log.setTotalCount(result.getTotalCount());
        log.setSuccessCount(result.getSuccessCount());
        log.setFailCount(result.getFailCount());
        log.setErrorMessage(truncate(result.getErrorMessage(), 2000));

        // 序列化详情和失败信息为 JSON
        try
        {
            if (result.getFailures() != null && !result.getFailures().isEmpty())
            {
                log.setFailedJson(objectMapper.writeValueAsString(result.getFailures()));
            }
        }
        catch (JsonProcessingException e)
        {
            LOG.warn("序列化失败明细JSON出错: {}", e.getMessage());
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

    private String truncate(String text, int maxLen)
    {
        if (text == null)
        {
            return null;
        }
        return text.length() <= maxLen ? text : text.substring(0, maxLen);
    }
}
