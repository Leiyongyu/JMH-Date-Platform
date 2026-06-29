package com.ruoyi.web.controller.operation;

import com.ruoyi.common.annotation.Log;
import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.enums.BusinessType;
import com.ruoyi.system.domain.operation.customs.CustomsDeclarationRequest;
import com.ruoyi.system.domain.operation.customs.CustomsProduct;
import com.ruoyi.system.domain.operation.customs.CustomsStockOrderLinkRequest;
import com.ruoyi.system.service.operation.customs.AmzFbaShipmentBoxExcelImportService;
import com.ruoyi.system.service.operation.customs.CustomsDeclarationExportService;
import com.ruoyi.system.service.operation.customs.CustomsProductService;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.servlet.http.HttpServletResponse;
import java.util.List;
import java.util.Map;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@Tag(name = "报关单制作")
@RestController
@RequestMapping("/operations/customs/declaration")
public class CustomsDeclarationController extends BaseController
{
    private final CustomsProductService productService;
    private final CustomsDeclarationExportService exportService;
    private final AmzFbaShipmentBoxExcelImportService shipmentBoxImportService;

    public CustomsDeclarationController(CustomsProductService productService,
                                        CustomsDeclarationExportService exportService,
                                        AmzFbaShipmentBoxExcelImportService shipmentBoxImportService)
    {
        this.productService = productService;
        this.exportService = exportService;
        this.shipmentBoxImportService = shipmentBoxImportService;
    }

    @PreAuthorize("@ss.hasPermi('customs:declaration:query')")
    @GetMapping("/products/search")
    public AjaxResult search(@RequestParam String keyword)
    {
        return success(productService.search(keyword));
    }

    @PreAuthorize("@ss.hasPermi('customs:declaration:query')")
    @PostMapping("/products/batch-query")
    public AjaxResult batchQuery(@RequestBody Map<String, List<String>> request)
    {
        return success(productService.batchQuery(request.get("skus"), null));
    }

    @PreAuthorize("@ss.hasPermi('customs:declaration:query')")
    @GetMapping("/stock-orders/search")
    public AjaxResult searchStockOrders(@RequestParam(required = false) String keyword,
                                        @RequestParam(required = false) Integer limit)
    {
        return success(productService.searchStockOrders(keyword, limit));
    }

    @PreAuthorize("@ss.hasPermi('customs:declaration:query')")
    @PostMapping("/stock-orders/products")
    public AjaxResult linkStockOrders(@RequestBody CustomsStockOrderLinkRequest request)
    {
        try { return success(productService.linkStockOrders(request == null ? null : request.getOverseasOrderNos())); }
        catch (Exception e) { return error(e.getMessage()); }
    }

    @PreAuthorize("@ss.hasPermi('customs:declaration:query')")
    @GetMapping("/fba-shipments/search")
    public AjaxResult searchFbaShipments(@RequestParam(required = false) String keyword,
                                         @RequestParam(required = false) Integer limit)
    {
        return success(productService.searchFbaShipments(keyword, limit));
    }

    @PreAuthorize("@ss.hasPermi('customs:declaration:query')")
    @PostMapping("/fba-shipments/products")
    public AjaxResult linkFbaShipments(@RequestBody CustomsStockOrderLinkRequest request)
    {
        try { return success(productService.linkFbaShipments(request == null ? null : request.getShipmentIds())); }
        catch (Exception e) { return error(e.getMessage()); }
    }

    @Log(title = "报关单-SKU批量导入", businessType = BusinessType.IMPORT)
    @PreAuthorize("@ss.hasPermi('customs:declaration:import')")
    @PostMapping("/import-skus")
    public AjaxResult importSkus(@RequestParam("file") MultipartFile file)
    {
        try { return success(productService.importSkuFile(file)); }
        catch (Exception e) { return error(e.getMessage()); }
    }

    @Log(title = "报关商品-历史报关单导入", businessType = BusinessType.IMPORT)
    @PreAuthorize("@ss.hasPermi('customs:declaration:import')")
    @PostMapping("/import-history")
    public AjaxResult importHistory(@RequestParam("file") MultipartFile file)
    {
        try { return success(productService.importHistory(file)); }
        catch (Exception e) { return error(e.getMessage()); }
    }

    @Log(title = "FBA装箱明细导入", businessType = BusinessType.IMPORT)
    @PreAuthorize("@ss.hasPermi('customs:declaration:import')")
    @PostMapping("/import-fba-shipment-box")
    public AjaxResult importFbaShipmentBox(@RequestParam("file") MultipartFile file)
    {
        try { return success(shipmentBoxImportService.importFile(file)); }
        catch (Exception e) { return error(e.getMessage()); }
    }

    @Log(title = "报关商品-保存主数据", businessType = BusinessType.UPDATE)
    @PreAuthorize("@ss.hasPermi('customs:product:edit')")
    @PutMapping("/products")
    public AjaxResult saveProducts(@RequestBody List<CustomsProduct> products,
                                   @RequestParam(value = "overwrite", defaultValue = "false") boolean overwrite)
    {
        try { return success(productService.saveProducts(products, overwrite)); }
        catch (Exception e) { return error(e.getMessage()); }
    }

    @PreAuthorize("@ss.hasPermi('customs:product:edit')")
    @PostMapping("/products/existing")
    public AjaxResult existingProducts(@RequestBody List<CustomsProduct> products)
    {
        try { return success(productService.findExistingProducts(products)); }
        catch (Exception e) { return error(e.getMessage()); }
    }

    @Log(title = "报关单导出", businessType = BusinessType.EXPORT)
    @PreAuthorize("@ss.hasPermi('customs:declaration:export')")
    @PostMapping("/export")
    public void export(@RequestBody CustomsDeclarationRequest request, HttpServletResponse response) throws Exception
    {
        exportService.export(request, response);
    }
}
