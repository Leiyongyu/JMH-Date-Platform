package com.ruoyi.web.controller.finance;

import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.core.page.TableDataInfo;
import com.ruoyi.system.service.finance.SlowMovingClearanceService;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** 财务中心滞销清货。 */
@Tag(name = "财务-滞销清货")
@RestController
@RequestMapping("/finance/slow-moving-clearance")
public class SlowMovingClearanceController extends BaseController
{
    private final SlowMovingClearanceService service;

    public SlowMovingClearanceController(SlowMovingClearanceService service)
    {
        this.service = service;
    }

    @PreAuthorize("@ss.hasPermi('finance:slowMovingClearance:list')")
    @GetMapping("/list")
    public TableDataInfo list(
            @RequestParam(required = false) String pullMonth)
    {
        startPage();
        return getDataTable(service.list(pullMonth));
    }

    @PreAuthorize("@ss.hasPermi('finance:slowMovingClearance:list')")
    @GetMapping("/summary")
    public AjaxResult summary(
            @RequestParam(required = false) String pullMonth)
    {
        return success(service.summary(pullMonth));
    }

}
