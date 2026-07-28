package com.ruoyi.web.controller.finance;

import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.page.TableDataInfo;
import com.ruoyi.common.annotation.Log;
import com.ruoyi.common.enums.BusinessType;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.system.service.finance.PerformanceRankingService;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

/** 财务中心绩效排名。 */
@Tag(name = "财务-绩效排名")
@RestController
@RequestMapping("/finance/performance-ranking")
public class PerformanceRankingController extends BaseController
{
    private final PerformanceRankingService service;

    public PerformanceRankingController(PerformanceRankingService service)
    {
        this.service = service;
    }

    @PreAuthorize("@ss.hasPermi('finance:performanceRanking:list')")
    @GetMapping("/list")
    public TableDataInfo list(
            @RequestParam(required = false) String statMonth,
            @RequestParam(required = false) String principalName)
    {
        startPage();
        return getDataTable(service.list(statMonth, principalName));
    }

    @Log(title = "Amazon绩效排名刷新", businessType = BusinessType.UPDATE)
    @PreAuthorize("@ss.hasPermi('finance:performanceRanking:edit')")
    @PostMapping("/refresh")
    public AjaxResult refresh(@RequestParam(required = false) String statMonth)
    {
        return success(service.refresh(statMonth));
    }
}
