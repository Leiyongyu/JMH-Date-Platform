package com.ruoyi.web.controller.operation;

import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.core.page.TableDataInfo;
import com.ruoyi.system.domain.operation.DataSyncLog;
import com.ruoyi.system.service.operation.IOperationSyncLogService;
import com.github.pagehelper.PageHelper;
import java.util.List;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

/**
 * 同步日志查看接口。
 */
@RestController
@RequestMapping("/operations/sync/log")
public class SyncLogController extends BaseController
{
    private final IOperationSyncLogService logService;

    public SyncLogController(IOperationSyncLogService logService) { this.logService = logService; }

    /** 分页列表 */
    @PreAuthorize("@ss.hasPermi('operations:syncLog:list')")
    @GetMapping("/list")
    public TableDataInfo list(@RequestParam(required = false) String syncType,
                               @RequestParam(required = false) String status,
                               @RequestParam(required = false) String triggerType)
    {
        startPage();
        List<DataSyncLog> list = logService.search(syncType, status, triggerType);
        return getDataTable(list);
    }

    /** 单条详情（含子步骤） */
    @PreAuthorize("@ss.hasPermi('operations:syncLog:list')")
    @GetMapping("/{id}")
    public AjaxResult detail(@PathVariable Long id)
    {
        DataSyncLog parent = logService.getById(id);
        List<DataSyncLog> children = logService.getChildren(id);
        AjaxResult r = AjaxResult.success();
        r.put("parent", parent);
        r.put("children", children);
        return r;
    }
}
