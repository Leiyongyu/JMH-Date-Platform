package com.ruoyi.system.mapper.operation;

import java.util.List;

import org.apache.ibatis.annotations.Param;

import com.ruoyi.system.domain.operation.OperationImportTask;

public interface OperationImportTaskMapper
{
    int insert(OperationImportTask task);
    int update(OperationImportTask task);
    OperationImportTask selectById(@Param("id") Long id);
    List<OperationImportTask> selectRecent(@Param("taskType") String taskType, @Param("limit") int limit);
}
