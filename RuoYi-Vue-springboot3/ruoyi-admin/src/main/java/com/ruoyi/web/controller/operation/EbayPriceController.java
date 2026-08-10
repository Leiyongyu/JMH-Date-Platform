package com.ruoyi.web.controller.operation;

import java.util.Map;
import java.util.UUID;
import java.util.concurrent.Semaphore;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;
import com.ruoyi.common.annotation.Log;
import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.enums.BusinessType;
import com.ruoyi.common.exception.ServiceException;
import com.ruoyi.common.utils.SecurityUtils;
import com.ruoyi.system.domain.operation.ebay.EbayPriceAuditReviewRequest;
import com.ruoyi.system.domain.operation.ebay.EbayPriceExportRequest;
import com.ruoyi.system.domain.operation.ebay.EbayPriceSearchRequest;
import com.ruoyi.system.service.operation.ebay.EbayOAuthTokenProvider;
import com.ruoyi.system.service.operation.ebay.EbayPriceAuditService;
import com.ruoyi.system.service.operation.ebay.EbayPriceExportService;
import com.ruoyi.system.service.operation.ebay.EbayPriceService;
import com.ruoyi.system.service.operation.ebay.EbaySkuOeImportService;
import io.swagger.v3.oas.annotations.tags.Tag;

@Tag(name = "eBay SP价格查询")
@RestController
@RequestMapping("/operation/ebay-price")
public class EbayPriceController extends BaseController
{
    private static final int MAX_CONCURRENT_TASKS = 3;
    private static final String BUSY_MESSAGE = "当前已有3个eBay查询或导出任务正在执行，请稍后再试";

    private final EbaySkuOeImportService importService;
    private final EbayPriceService priceService;
    private final EbayPriceExportService exportService;
    private final EbayPriceAuditService auditService;
    private final EbayOAuthTokenProvider tokenProvider;
    private final Semaphore taskPermits = new Semaphore(MAX_CONCURRENT_TASKS, true);

    public EbayPriceController(EbaySkuOeImportService importService,
            EbayPriceService priceService, EbayPriceExportService exportService,
            EbayOAuthTokenProvider tokenProvider, EbayPriceAuditService auditService)
    {
        this.importService = importService;
        this.priceService = priceService;
        this.exportService = exportService;
        this.tokenProvider = tokenProvider;
        this.auditService = auditService;
    }

    @PreAuthorize("@ss.hasPermi('scripts:ebayPrice:list')")
    @GetMapping("/health")
    public AjaxResult health()
    {
        return AjaxResult.success(Map.of(
                "name", "ebay",
                "status", tokenProvider.isConfigured() ? "ok" : "not_configured",
                "configured", tokenProvider.isConfigured()));
    }

    @Log(title = "eBay SKU-OE对照表", businessType = BusinessType.IMPORT)
    @PreAuthorize("@ss.hasPermi('scripts:ebayPrice:import')")
    @PostMapping("/sku-oe-imports")
    public AjaxResult importSkuOe(@RequestParam("file") MultipartFile file,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId)
    {
        String actualRequestId = requestId(requestId);
        AjaxResult result = AjaxResult.success("SKU-OE 对照表导入成功", importService.importMappings(file));
        result.put("request_id", actualRequestId);
        return result;
    }

    @Log(title = "eBay SP价格查询", businessType = BusinessType.OTHER)
    @PreAuthorize("@ss.hasPermi('scripts:ebayPrice:query')")
    @PostMapping("/searches")
    public AjaxResult search(@RequestBody EbayPriceSearchRequest request,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId)
    {
        acquireTaskPermit();
        try
        {
            String actualRequestId = requestId(requestId);
            AjaxResult result = AjaxResult.success(priceService.search(request, actualRequestId));
            result.put("request_id", actualRequestId);
            return result;
        }
        finally
        {
            taskPermits.release();
        }
    }

    @Log(title = "eBay SP价格查询", businessType = BusinessType.EXPORT)
    @PreAuthorize("@ss.hasPermi('scripts:ebayPrice:export')")
    @PostMapping("/exports")
    public void export(@RequestBody EbayPriceExportRequest request, HttpServletResponse response,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId)
    {
        acquireTaskPermit();
        try
        {
            String actualRequestId = requestId(requestId);
            exportService.export(request == null ? null : request.getItems(), response, actualRequestId);
        }
        finally
        {
            taskPermits.release();
        }
    }

    @Log(title = "eBay价格批量审核", businessType = BusinessType.IMPORT)
    @PreAuthorize("@ss.hasPermi('scripts:ebayPrice:query')")
    @PostMapping("/audit-tasks")
    public AjaxResult createAuditTask(@RequestParam("file") MultipartFile file,
            @RequestParam(value = "site", defaultValue = "de") String site,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId)
    {
        String actualRequestId = requestId(requestId);
        AjaxResult result = AjaxResult.success("文件读取成功，后台查询已开始",
                auditService.createTask(file, site, SecurityUtils.getUserId(), SecurityUtils.getUsername()));
        result.put("request_id", actualRequestId);
        return result;
    }

    @PreAuthorize("@ss.hasPermi('scripts:ebayPrice:list')")
    @GetMapping("/audit-tasks/latest")
    public AjaxResult latestAuditTask()
    {
        return AjaxResult.success(auditService.latestTask(SecurityUtils.getUserId()));
    }

    @PreAuthorize("@ss.hasPermi('scripts:ebayPrice:list')")
    @GetMapping("/audit-tasks")
    public AjaxResult auditTasks()
    {
        return AjaxResult.success(auditService.recentTasks(SecurityUtils.getUserId()));
    }

    @PreAuthorize("@ss.hasPermi('scripts:ebayPrice:list')")
    @GetMapping("/audit-tasks/{taskId}")
    public AjaxResult auditTask(@PathVariable Long taskId)
    {
        return AjaxResult.success(auditService.taskView(taskId, SecurityUtils.getUserId()));
    }

    @PreAuthorize("@ss.hasPermi('scripts:ebayPrice:list')")
    @GetMapping("/audit-tasks/{taskId}/oes/{oeId}")
    public AjaxResult auditOe(@PathVariable Long taskId, @PathVariable Long oeId)
    {
        return AjaxResult.success(auditService.oeView(taskId, oeId, SecurityUtils.getUserId()));
    }

    @Log(title = "eBay价格人工审核", businessType = BusinessType.UPDATE)
    @PreAuthorize("@ss.hasPermi('scripts:ebayPrice:query')")
    @PutMapping("/audit-tasks/{taskId}/oes/{oeId}/review")
    public AjaxResult reviewAuditOe(@PathVariable Long taskId, @PathVariable Long oeId,
            @RequestBody EbayPriceAuditReviewRequest request)
    {
        return AjaxResult.success("审核结果已保存", auditService.review(taskId, oeId, request,
                SecurityUtils.getUserId(), SecurityUtils.getUsername()));
    }

    @Log(title = "eBay价格查询重试", businessType = BusinessType.OTHER)
    @PreAuthorize("@ss.hasPermi('scripts:ebayPrice:query')")
    @PostMapping("/audit-tasks/{taskId}/oes/{oeId}/retry")
    public AjaxResult retryAuditOe(@PathVariable Long taskId, @PathVariable Long oeId)
    {
        return AjaxResult.success("已重新提交查询", auditService.retry(taskId, oeId, SecurityUtils.getUserId()));
    }

    @Log(title = "eBay价格审核结果", businessType = BusinessType.EXPORT)
    @PreAuthorize("@ss.hasPermi('scripts:ebayPrice:export')")
    @PostMapping("/audit-tasks/{taskId}/exports")
    public void exportAuditTask(@PathVariable Long taskId, HttpServletResponse response,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId)
    {
        acquireTaskPermit();
        try
        {
            exportService.export(auditService.selectedItemsForExport(taskId, SecurityUtils.getUserId()),
                    response, requestId(requestId));
        }
        finally
        {
            taskPermits.release();
        }
    }

    private void acquireTaskPermit()
    {
        if (!taskPermits.tryAcquire())
        {
            throw new ServiceException(BUSY_MESSAGE);
        }
    }

    private static String requestId(String value)
    {
        return value == null || value.trim().isEmpty()
                ? UUID.randomUUID().toString().replace("-", "")
                : value.trim();
    }
}
