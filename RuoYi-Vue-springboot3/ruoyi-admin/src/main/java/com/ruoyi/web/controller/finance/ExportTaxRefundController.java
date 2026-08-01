package com.ruoyi.web.controller.finance;

import com.ruoyi.common.annotation.Log;
import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.enums.BusinessType;
import com.ruoyi.system.service.finance.TaxRefundDataProjectClient;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

/** 财务中心外汇退税，统一代理当前 Date-Project 服务。 */
@Tag(name = "财务-外汇退税")
@RestController
@RequestMapping("/finance/export-tax-refund")
public class ExportTaxRefundController extends BaseController
{
    private final TaxRefundDataProjectClient pythonClient;

    public ExportTaxRefundController(
            TaxRefundDataProjectClient pythonClient)
    {
        this.pythonClient = pythonClient;
    }

    @Log(title = "外汇退税-导入报关资料文件夹",
            businessType = BusinessType.IMPORT)
    @PreAuthorize("@ss.hasPermi('finance:exportTaxRefund:import')")
    @PostMapping("/imports/customs-folder")
    public AjaxResult importCustomsFolder(
            @RequestParam("files") MultipartFile[] files)
    {
        return invoke(() -> pythonClient.importCustomsFolder(
                files, getUsername()));
    }

    @Log(title = "外汇退税-导入采购发票汇总",
            businessType = BusinessType.IMPORT)
    @PreAuthorize("@ss.hasPermi('finance:exportTaxRefund:import')")
    @PostMapping("/imports/purchase-invoice-summary")
    public AjaxResult importPurchaseInvoiceSummary(
            @RequestParam("file") MultipartFile file)
    {
        return invoke(() -> pythonClient.importPurchaseInvoice(
                file, getUsername()));
    }

    @Log(title = "外汇退税-导入外汇回款",
            businessType = BusinessType.IMPORT)
    @PreAuthorize("@ss.hasPermi('finance:exportTaxRefund:import')")
    @PostMapping("/imports/foreign-exchange-receipts")
    public AjaxResult importForeignExchangeReceipts(
            @RequestParam("file") MultipartFile file)
    {
        return invoke(() -> pythonClient.importForeignExchange(
                file, getUsername()));
    }

    @PreAuthorize("@ss.hasPermi('finance:exportTaxRefund:query')")
    @GetMapping("/import-jobs/{jobId}")
    public AjaxResult getImportJob(@PathVariable String jobId)
    {
        return invoke(() -> pythonClient.getImportJob(jobId));
    }

    @PreAuthorize("@ss.hasPermi('finance:exportTaxRefund:query')")
    @GetMapping("/customs-declarations")
    public AjaxResult customsDeclarations()
    {
        return invoke(pythonClient::customsDeclarations);
    }

    @Log(title = "外汇退税-生成申报批次",
            businessType = BusinessType.INSERT)
    @PreAuthorize("@ss.hasPermi('finance:exportTaxRefund:generate')")
    @PostMapping("/declaration-batches")
    public AjaxResult createDeclarationBatch(
            @RequestBody Map<String, Object> payload)
    {
        return invoke(() -> pythonClient.createDeclarationBatch(payload));
    }

    @Log(title = "外汇退税-生成最终资料包",
            businessType = BusinessType.INSERT)
    @PreAuthorize("@ss.hasPermi('finance:exportTaxRefund:generate')")
    @PostMapping("/packages")
    public AjaxResult generatePackage(
            @RequestBody(required = false) Map<String, Object> payload)
    {
        return invoke(() -> pythonClient.generatePackage(payload));
    }

    @PreAuthorize("@ss.hasPermi('finance:exportTaxRefund:export')")
    @GetMapping("/packages/latest/file")
    public ResponseEntity<byte[]> downloadLatestPackage()
    {
        byte[] file = pythonClient.downloadLatestPackage();
        String filename = URLEncoder.encode(
                "外汇退税生成文件.zip", StandardCharsets.UTF_8)
                .replace("+", "%20");
        return ResponseEntity.ok()
                .header(HttpHeaders.CONTENT_DISPOSITION,
                        "attachment; filename*=UTF-8''" + filename)
                .contentType(MediaType.APPLICATION_OCTET_STREAM)
                .contentLength(file.length)
                .body(file);
    }

    @PreAuthorize("@ss.hasPermi('finance:exportTaxRefund:query')")
    @GetMapping("/inventory")
    public AjaxResult inventory(
            @RequestParam Map<String, Object> params)
    {
        try
        {
            Map<String, Object> response = pythonClient.inventory(params);
            Object data = response.containsKey("data")
                    ? response.get("data")
                    : response;
            return success(data);
        }
        catch (Exception e)
        {
            return error(e.getMessage());
        }
    }

    private AjaxResult invoke(Action action)
    {
        try
        {
            return success(action.run());
        }
        catch (Exception e)
        {
            return error(e.getMessage());
        }
    }

    @FunctionalInterface
    private interface Action
    {
        Object run();
    }
}
