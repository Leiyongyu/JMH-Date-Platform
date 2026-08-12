package com.ruoyi.web.controller.sop;

import com.ruoyi.common.annotation.Log;
import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.core.page.TableDataInfo;
import com.ruoyi.common.enums.BusinessType;
import com.ruoyi.system.domain.operation.ebay.EbayCompetitorProduct;
import com.ruoyi.system.domain.operation.ebay.EbayCompetitorQueryRequest;
import com.ruoyi.system.domain.operation.ebay.EbayCompetitorExportRequest;
import com.ruoyi.system.service.operation.ebay.EbayCompetitorExcelService;
import com.ruoyi.system.service.operation.ebay.EbayCompetitorService;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** SOP-eBay选竞品商品库与利润测算。 */
@Tag(name = "SOP-eBay查竞品")
@RestController
@RequestMapping("/sop/competitor")
public class EbayCompetitorController extends BaseController
{
    private final EbayCompetitorService competitorService;
    private final EbayCompetitorExcelService excelService;

    public EbayCompetitorController(EbayCompetitorService competitorService,
            EbayCompetitorExcelService excelService)
    {
        this.competitorService = competitorService;
        this.excelService = excelService;
    }

    @PreAuthorize("@ss.hasPermi('sop:competitor:list')")
    @GetMapping("/list")
    public TableDataInfo list(EbayCompetitorProduct query)
    {
        startPage();
        return getDataTable(competitorService.listProducts(query));
    }

    @Log(title = "eBay竞品链接查询", businessType = BusinessType.OTHER)
    @PreAuthorize("@ss.hasPermi('sop:competitor:query')")
    @PostMapping("/query")
    public AjaxResult query(@RequestBody(required = false) EbayCompetitorQueryRequest request)
    {
        return AjaxResult.success(competitorService.queryByUrl(
                request == null ? null : request.getUrl()));
    }

    @Log(title = "导入eBay竞品链接", businessType = BusinessType.IMPORT)
    @PreAuthorize("@ss.hasPermi('sop:competitor:import')")
    @PostMapping("/import-links")
    public AjaxResult importLinks(@RequestParam("file") MultipartFile file)
    {
        return AjaxResult.success(excelService.parseLinkFile(file));
    }

    @Log(title = "导出eBay竞品商品库", businessType = BusinessType.EXPORT)
    @PreAuthorize("@ss.hasPermi('sop:competitor:export')")
    @PostMapping("/export")
    public void export(@RequestBody(required = false) EbayCompetitorExportRequest request,
            HttpServletResponse response)
    {
        excelService.exportProducts(request, response);
    }

    @Log(title = "保存eBay竞品", businessType = BusinessType.INSERT)
    @PreAuthorize("@ss.hasPermi('sop:competitor:save')")
    @PostMapping("/save")
    public AjaxResult save(@RequestBody EbayCompetitorProduct product)
    {
        return AjaxResult.success(competitorService.saveProduct(product, getUsername()));
    }

    @Log(title = "编辑eBay竞品", businessType = BusinessType.UPDATE)
    @PreAuthorize("@ss.hasPermi('sop:competitor:edit')")
    @PutMapping("/{id}")
    public AjaxResult update(@PathVariable Long id, @RequestBody EbayCompetitorProduct product)
    {
        return AjaxResult.success(competitorService.updateProduct(id, product, getUsername()));
    }

    @Log(title = "删除eBay竞品", businessType = BusinessType.DELETE)
    @PreAuthorize("@ss.hasPermi('sop:competitor:remove')")
    @DeleteMapping("/{id}")
    public AjaxResult remove(@PathVariable Long id)
    {
        return toAjax(competitorService.deleteProduct(id));
    }
}
