package com.ruoyi.web.controller.finance;

import com.ruoyi.common.annotation.Log;
import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.enums.BusinessType;
import com.ruoyi.system.service.finance.TaxRefundPythonClient;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@Tag(name = "财务-eBay财务")
@RestController
@RequestMapping("/finance/ebay-finance")
public class EbayFinanceController extends BaseController
{
    private final TaxRefundPythonClient pythonClient;

    public EbayFinanceController(TaxRefundPythonClient pythonClient)
    {
        this.pythonClient = pythonClient;
    }

    @PreAuthorize("@ss.hasPermi('finance:ebayFinance:list')")
    @GetMapping("/list")
    public AjaxResult list(@RequestParam Map<String, Object> params)
    {
        try
        {
            return table(pythonClient.listEbayFinance(toPythonPageParams(params)));
        }
        catch (Exception e)
        {
            return error(e.getMessage());
        }
    }

    @PreAuthorize("@ss.hasPermi('finance:ebayFinance:list')")
    @GetMapping("/imports")
    public AjaxResult imports(@RequestParam Map<String, Object> params)
    {
        try
        {
            return table(pythonClient.listEbayFinanceImports(toPythonPageParams(params)));
        }
        catch (Exception e)
        {
            return error(e.getMessage());
        }
    }

    @PreAuthorize("@ss.hasPermi('finance:ebayFinance:list')")
    @GetMapping("/{id}")
    public AjaxResult getInfo(@PathVariable Long id)
    {
        try
        {
            return success(data(pythonClient.getEbayFinance(id)));
        }
        catch (Exception e)
        {
            return error(e.getMessage());
        }
    }

    @Log(title = "eBay财务-导入酷长利润", businessType = BusinessType.IMPORT)
    @PreAuthorize("@ss.hasPermi('finance:ebayFinance:import')")
    @PostMapping("/import")
    public AjaxResult importChiefProfit(@RequestParam("file") MultipartFile file)
    {
        try
        {
            return success(data(pythonClient.importEbayFinance(file, getUsername())));
        }
        catch (Exception e)
        {
            return error(e.getMessage());
        }
    }

    @Log(title = "eBay财务-编辑利润明细", businessType = BusinessType.UPDATE)
    @PreAuthorize("@ss.hasPermi('finance:ebayFinance:edit')")
    @PutMapping("/{id}")
    public AjaxResult update(@PathVariable Long id, @RequestBody Map<String, Object> payload)
    {
        try
        {
            pythonClient.updateEbayFinance(id, payload, getUsername());
            return success();
        }
        catch (Exception e)
        {
            return error(e.getMessage());
        }
    }

    private Map<String, Object> toPythonPageParams(Map<String, Object> params)
    {
        Map<String, Object> result = new LinkedHashMap<>(params);
        move(result, "pageNum", "page");
        move(result, "pageSize", "page_size");
        move(result, "periodStart", "period_start");
        move(result, "periodEnd", "period_end");
        return result;
    }

    private void move(Map<String, Object> params, String source, String target)
    {
        Object value = params.remove(source);
        if (value != null)
        {
            params.put(target, value);
        }
    }

    @SuppressWarnings("unchecked")
    private Object data(Map<String, Object> response)
    {
        return response.get("data");
    }

    @SuppressWarnings("unchecked")
    private AjaxResult table(Map<String, Object> response)
    {
        AjaxResult result = AjaxResult.success();
        result.put("rows", response.getOrDefault("data", java.util.List.of()));
        Object metaValue = response.get("meta");
        Object total = metaValue instanceof Map<?, ?> meta ? meta.get("total") : 0;
        result.put("total", total == null ? 0 : total);
        return result;
    }
}
