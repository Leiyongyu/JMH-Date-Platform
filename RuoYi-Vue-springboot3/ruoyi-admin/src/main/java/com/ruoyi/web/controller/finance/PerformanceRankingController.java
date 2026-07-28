package com.ruoyi.web.controller.finance;

import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.page.TableDataInfo;
import com.ruoyi.common.annotation.Log;
import com.ruoyi.common.enums.BusinessType;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.system.service.finance.CombinedPerformanceRankingService;
import com.ruoyi.system.service.finance.EbayPerformanceImportService;
import com.ruoyi.system.service.finance.EbayPerformanceRankingService;
import com.ruoyi.system.service.finance.PerformanceOwnerRuleImportService;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

/** 财务中心绩效排名。 */
@Tag(name = "财务-绩效排名")
@RestController
@RequestMapping("/finance/performance-ranking")
public class PerformanceRankingController extends BaseController
{
    private final CombinedPerformanceRankingService combinedService;
    private final PerformanceOwnerRuleImportService ownerRuleImportService;
    private final EbayPerformanceRankingService ebayService;
    private final EbayPerformanceImportService ebayImportService;

    public PerformanceRankingController(
            CombinedPerformanceRankingService combinedService,
            PerformanceOwnerRuleImportService ownerRuleImportService,
            EbayPerformanceRankingService ebayService,
            EbayPerformanceImportService ebayImportService)
    {
        this.combinedService = combinedService;
        this.ownerRuleImportService = ownerRuleImportService;
        this.ebayService = ebayService;
        this.ebayImportService = ebayImportService;
    }

    @PreAuthorize("@ss.hasPermi('finance:performanceRanking:list')")
    @GetMapping("/list")
    public TableDataInfo list(
            @RequestParam(required = false) String statMonth,
            @RequestParam(required = false) String principalName)
    {
        startPage();
        return getDataTable(combinedService.list(statMonth, principalName));
    }

    @Log(title = "综合绩效排名刷新", businessType = BusinessType.UPDATE)
    @PreAuthorize("@ss.hasPermi('finance:performanceRanking:edit')")
    @PostMapping("/refresh")
    public AjaxResult refresh(@RequestParam(required = false) String statMonth)
    {
        return success(combinedService.refresh(statMonth));
    }

    @Log(title = "Amazon绩效负责人规则导入", businessType = BusinessType.IMPORT)
    @PreAuthorize("@ss.hasPermi('finance:performanceRanking:edit')")
    @PostMapping("/owner-rules/import")
    public AjaxResult importOwnerRules(@RequestParam("file") MultipartFile file) throws Exception
    {
        return success(ownerRuleImportService.importFile(file, getUsername()));
    }

    @PreAuthorize("@ss.hasPermi('finance:performanceRanking:list')")
    @GetMapping("/owner-rules/summary")
    public AjaxResult ownerRuleSummary(@RequestParam String statMonth)
    {
        return success(ownerRuleImportService.summary(statMonth));
    }

    @PreAuthorize("@ss.hasPermi('finance:performanceRanking:list')")
    @GetMapping("/ebay/list")
    public TableDataInfo ebayList(
            @RequestParam(required = false) String statMonth,
            @RequestParam(required = false) String principalName)
    {
        startPage();
        return getDataTable(ebayService.list(statMonth, principalName));
    }

    @Log(title = "eBay绩效排名刷新", businessType = BusinessType.UPDATE)
    @PreAuthorize("@ss.hasPermi('finance:performanceRanking:edit')")
    @PostMapping("/ebay/refresh")
    public AjaxResult refreshEbay(@RequestParam(required = false) String statMonth)
    {
        return success(ebayService.refresh(statMonth));
    }

    @Log(title = "eBay月度绩效利润导入", businessType = BusinessType.IMPORT)
    @PreAuthorize("@ss.hasPermi('finance:performanceRanking:edit')")
    @PostMapping("/ebay/profit/import")
    public AjaxResult importEbayProfit(
            @RequestParam("file") MultipartFile file) throws Exception
    {
        return success(ebayImportService.importProfit(file, getUsername()));
    }

    @Log(title = "eBay绩效负责人规则导入", businessType = BusinessType.IMPORT)
    @PreAuthorize("@ss.hasPermi('finance:performanceRanking:edit')")
    @PostMapping("/ebay/owner-rules/import")
    public AjaxResult importEbayOwnerRules(
            @RequestParam("file") MultipartFile file) throws Exception
    {
        return success(ebayImportService.importOwnerRules(file, getUsername()));
    }

    @PreAuthorize("@ss.hasPermi('finance:performanceRanking:list')")
    @GetMapping("/ebay/owner-rules/summary")
    public AjaxResult ebayOwnerRuleSummary(@RequestParam String statMonth)
    {
        return success(ebayImportService.ownerRuleSummary(statMonth));
    }
}
