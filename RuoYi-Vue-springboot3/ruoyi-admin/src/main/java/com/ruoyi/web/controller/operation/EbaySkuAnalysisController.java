package com.ruoyi.web.controller.operation;

import com.ruoyi.common.annotation.Log;
import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.enums.BusinessType;
import com.ruoyi.system.service.operation.ebay.EbaySkuAnalysisPythonClient;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

import java.util.LinkedHashMap;
import java.util.Map;

/** 运营中心-eBay SKU分析。 */
@Tag(name = "运营中心-eBay SKU分析")
@RestController
@RequestMapping("/operations/ebay/sku-analysis")
public class EbaySkuAnalysisController extends BaseController
{
    private final EbaySkuAnalysisPythonClient client;
    public EbaySkuAnalysisController(EbaySkuAnalysisPythonClient client) { this.client = client; }

    @PreAuthorize("@ss.hasPermi('operations:ebaySkuAnalysis:list')")
    @GetMapping("/dates")
    public AjaxResult dates(@RequestHeader(value = "X-Request-ID", required = false) String requestId)
    { return success(data(client.dates(requestId))); }

    @PreAuthorize("@ss.hasPermi('operations:ebaySkuAnalysis:list')")
    @GetMapping("/summary")
    public AjaxResult summary(@RequestParam(required = false) String startDate,
            @RequestParam(required = false) String endDate, @RequestParam(required = false) String sku,
            @RequestParam(required = false) String site,
            @RequestParam(defaultValue = "paid_amount") String chartMetric,
            @RequestParam(defaultValue = "desc") String chartOrder,
            @RequestParam(defaultValue = "1") int pageNum, @RequestParam(defaultValue = "50") int pageSize,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId)
    {
        Map<String, Object> params = new LinkedHashMap<>();
        params.put("start_date", startDate); params.put("end_date", endDate); params.put("sku", sku);
        params.put("site", site); params.put("chart_metric", chartMetric); params.put("chart_order", chartOrder);
        params.put("page", pageNum); params.put("page_size", pageSize);
        return success(data(client.summary(params, requestId)));
    }

    @PreAuthorize("@ss.hasPermi('operations:ebayReturnDetail:list')")
    @GetMapping("/return-details")
    public AjaxResult returnDetails(@RequestParam(required = false) String startDate,
            @RequestParam(required = false) String endDate,
            @RequestParam(defaultValue = "refund") String timeType,
            @RequestParam(required = false) String sku,
            @RequestParam(required = false) String site,
            @RequestParam(required = false) String orderNo,
            @RequestParam(defaultValue = "1") int pageNum,
            @RequestParam(defaultValue = "50") int pageSize,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId)
    {
        Map<String, Object> params = new LinkedHashMap<>();
        params.put("start_date", startDate); params.put("end_date", endDate);
        params.put("time_type", timeType); params.put("sku", sku);
        params.put("site", site); params.put("order_no", orderNo);
        params.put("page", pageNum); params.put("page_size", pageSize);
        return success(data(client.returnDetails(params, requestId)));
    }

    @PreAuthorize("@ss.hasPermi('operations:ebayReturnOverview:list')")
    @GetMapping("/return-overview/metrics")
    public AjaxResult returnOverviewMetrics(@RequestParam(required = false) String startDate,
            @RequestParam(required = false) String endDate,
            @RequestParam(defaultValue = "payment") String timeType,
            @RequestParam(required = false) String sku,
            @RequestParam(required = false) String site,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId)
    {
        Map<String, Object> params = new LinkedHashMap<>();
        params.put("start_date", startDate); params.put("end_date", endDate);
        params.put("time_type", timeType); params.put("sku", sku); params.put("site", site);
        return success(data(client.returnOverviewMetrics(params, requestId)));
    }

    @PreAuthorize("@ss.hasPermi('operations:ebayReturnDetail:list')")
    @GetMapping("/return-categories")
    public AjaxResult returnCategories(
            @RequestHeader(value = "X-Request-ID", required = false) String requestId)
    {
        return success(data(client.returnCategories(requestId)));
    }

    @Log(title = "eBay退货明细售后分类", businessType = BusinessType.UPDATE)
    @PreAuthorize("@ss.hasPermi('operations:ebayReturnDetail:list')")
    @PostMapping("/return-classification")
    public AjaxResult saveReturnClassification(@RequestBody Map<String, Object> payload,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId)
    {
        return success(data(client.saveReturnClassification(payload, getUsername(), requestId)));
    }

    @Log(title = "eBay SKU分析订单导入", businessType = BusinessType.IMPORT)
    @PreAuthorize("@ss.hasPermi('operations:ebaySkuAnalysis:import')")
    @PostMapping("/import")
    public AjaxResult importOrders(@RequestParam("file") MultipartFile file,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId)
    { return success(data(client.importOrders(file, getUsername(), requestId))); }

    private Object data(Map<String, Object> response) { return response.get("data"); }
}
