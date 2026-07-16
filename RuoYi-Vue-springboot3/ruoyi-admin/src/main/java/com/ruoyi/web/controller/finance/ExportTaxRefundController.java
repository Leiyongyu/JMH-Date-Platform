package com.ruoyi.web.controller.finance;

import com.ruoyi.common.annotation.Log;
import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.enums.BusinessType;
import com.ruoyi.system.service.finance.TaxRefundPythonClient;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.HashMap;
import java.util.Map;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@Tag(name = "财务-外汇退税")
@RestController
@RequestMapping("/finance/export-tax-refund")
public class ExportTaxRefundController extends BaseController
{
    private final TaxRefundPythonClient pythonClient;

    public ExportTaxRefundController(TaxRefundPythonClient pythonClient)
    {
        this.pythonClient = pythonClient;
    }

    @Log(title = "外汇退税-导入报关资料", businessType = BusinessType.IMPORT)
    @PreAuthorize("@ss.hasPermi('finance:exportTaxRefund:import')")
    @PostMapping("/tasks/customs-material")
    public AjaxResult importCustomsMaterial(@RequestParam("file") MultipartFile file)
    {
        try
        {
            return success(pythonClient.createFileTask("CUSTOMS_MATERIAL_IMPORT", file, Map.of(), getUsername()));
        }
        catch (Exception e)
        {
            return error(e.getMessage());
        }
    }

    @Log(title = "外汇退税-导入报关单", businessType = BusinessType.IMPORT)
    @PreAuthorize("@ss.hasPermi('finance:exportTaxRefund:import')")
    @PostMapping("/tasks/customs-declaration")
    public AjaxResult importCustomsDeclaration(@RequestParam("file") MultipartFile file,
                                               @RequestParam(required = false) String declarationMonth,
                                               @RequestParam(required = false) String declarationBatch,
                                               @RequestParam(required = false) String exportDate)
    {
        try
        {
            Map<String, String> fields = new HashMap<>();
            fields.put("declaration_month", declarationMonth);
            fields.put("declaration_batch", declarationBatch);
            fields.put("export_date", exportDate);
            return success(pythonClient.createFileTask("CUSTOMS_DECLARATION_IMPORT", file, fields, getUsername()));
        }
        catch (Exception e)
        {
            return error(e.getMessage());
        }
    }

    @Log(title = "外汇退税-导入进货发票", businessType = BusinessType.IMPORT)
    @PreAuthorize("@ss.hasPermi('finance:exportTaxRefund:import')")
    @PostMapping("/tasks/purchase-invoice")
    public AjaxResult importPurchaseInvoice(@RequestParam("file") MultipartFile file)
    {
        try
        {
            return success(pythonClient.createFileTask("PURCHASE_INVOICE_IMPORT", file, Map.of(), getUsername()));
        }
        catch (Exception e)
        {
            return error(e.getMessage());
        }
    }

    @Log(title = "外汇退税-导入外汇数据", businessType = BusinessType.IMPORT)
    @PreAuthorize("@ss.hasPermi('finance:exportTaxRefund:import')")
    @PostMapping("/tasks/forex")
    public AjaxResult importForex(@RequestParam("file") MultipartFile file)
    {
        try
        {
            return success(pythonClient.createFileTask("FOREX_IMPORT", file, Map.of(), getUsername()));
        }
        catch (Exception e)
        {
            return error(e.getMessage());
        }
    }

    @Log(title = "外汇退税-生成退税资料", businessType = BusinessType.INSERT)
    @PreAuthorize("@ss.hasPermi('finance:exportTaxRefund:generate')")
    @PostMapping("/tasks/refund-package")
    public AjaxResult generateRefundPackage(@RequestBody Map<String, Object> payload)
    {
        try
        {
            Map<String, Object> request = payload == null ? new HashMap<>() : new HashMap<>(payload);
            request.put("task_type", "REFUND_PACKAGE_GENERATE");
            return success(pythonClient.createJsonTask(request, getUsername()));
        }
        catch (Exception e)
        {
            return error(e.getMessage());
        }
    }

    @PreAuthorize("@ss.hasPermi('finance:exportTaxRefund:query')")
    @GetMapping("/tasks/{taskId}")
    public AjaxResult getTask(@PathVariable Long taskId)
    {
        try
        {
            return success(pythonClient.getTask(taskId));
        }
        catch (Exception e)
        {
            return error(e.getMessage());
        }
    }

    @PreAuthorize("@ss.hasPermi('finance:exportTaxRefund:query')")
    @GetMapping("/tasks")
    public AjaxResult listTasks(@RequestParam Map<String, Object> params)
    {
        try
        {
            return success(pythonClient.listTasks(params));
        }
        catch (Exception e)
        {
            return error(e.getMessage());
        }
    }

    @PreAuthorize("@ss.hasPermi('finance:exportTaxRefund:query')")
    @GetMapping("/customs-material-items")
    public AjaxResult listCustomsMaterialItems(@RequestParam Map<String, Object> params)
    {
        try
        {
            return success(pythonClient.listCustomsMaterialItems(params));
        }
        catch (Exception e)
        {
            return error(e.getMessage());
        }
    }

    @PreAuthorize("@ss.hasPermi('finance:exportTaxRefund:query')")
    @GetMapping("/export-details")
    public AjaxResult listExportDetails(@RequestParam Map<String, Object> params)
    {
        try
        {
            return success(pythonClient.listExportDetails(params));
        }
        catch (Exception e)
        {
            return error(e.getMessage());
        }
    }

    @PreAuthorize("@ss.hasPermi('finance:exportTaxRefund:query')")
    @GetMapping("/purchase-inventory")
    public AjaxResult listPurchaseInventory(@RequestParam Map<String, Object> params)
    {
        try
        {
            return success(pythonClient.listPurchaseInventory(params));
        }
        catch (Exception e)
        {
            return error(e.getMessage());
        }
    }

    @PreAuthorize("@ss.hasPermi('finance:exportTaxRefund:query')")
    @GetMapping("/forex-receivables")
    public AjaxResult listForexReceivables(@RequestParam Map<String, Object> params)
    {
        try
        {
            return success(pythonClient.listForexReceivables(params));
        }
        catch (Exception e)
        {
            return error(e.getMessage());
        }
    }
}
