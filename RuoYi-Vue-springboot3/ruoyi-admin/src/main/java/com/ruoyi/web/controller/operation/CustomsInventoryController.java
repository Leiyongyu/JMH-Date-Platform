package com.ruoyi.web.controller.operation;

import com.ruoyi.common.annotation.Log;
import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.core.page.TableDataInfo;
import com.ruoyi.common.enums.BusinessType;
import com.ruoyi.system.domain.operation.customs.CustomsInventoryItem;
import com.ruoyi.system.service.operation.customs.CustomsInventoryService;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.servlet.http.HttpServletResponse;
import java.util.List;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@Tag(name = "报关出入库清单")
@RestController
@RequestMapping("/operations/customs/inventory")
public class CustomsInventoryController extends BaseController
{
    private final CustomsInventoryService inventoryService;

    public CustomsInventoryController(CustomsInventoryService inventoryService)
    {
        this.inventoryService = inventoryService;
    }

    @PreAuthorize("@ss.hasPermi('customs:inventory:list')")
    @GetMapping("/list")
    public TableDataInfo list(@RequestParam(required = false) String keyword)
    {
        startPage();
        List<CustomsInventoryItem> list = inventoryService.list(keyword);
        return getDataTable(list);
    }

    @PreAuthorize("@ss.hasPermi('customs:inventory:list')")
    @GetMapping("/product-options")
    public AjaxResult productOptions(@RequestParam(required = false) String productCode,
                                     @RequestParam(required = false) String productName,
                                     @RequestParam(required = false) String sku,
                                     @RequestParam(required = false) String unit)
    {
        return success(inventoryService.productOptions(productCode, productName, sku, unit));
    }

    @PreAuthorize("@ss.hasPermi('customs:inventory:edit')")
    @GetMapping("/editable-fields")
    public AjaxResult editableFields()
    {
        return success(inventoryService.editableFields());
    }

    @Log(title = "报关出入库清单导入", businessType = BusinessType.IMPORT)
    @PreAuthorize("@ss.hasPermi('customs:inventory:import')")
    @PostMapping("/import")
    public AjaxResult importFile(@RequestParam("file") MultipartFile file)
    {
        try { return success(inventoryService.importFile(file)); }
        catch (Exception e) { return error(e.getMessage()); }
    }

    @Log(title = "报关出入库清单新增", businessType = BusinessType.INSERT)
    @PreAuthorize("@ss.hasPermi('customs:inventory:add')")
    @PostMapping
    public AjaxResult add(@RequestBody CustomsInventoryItem item)
    {
        try { return success(inventoryService.add(item)); }
        catch (Exception e) { return error(e.getMessage()); }
    }

    @Log(title = "报关出入库清单编辑", businessType = BusinessType.UPDATE)
    @PreAuthorize("@ss.hasPermi('customs:inventory:edit')")
    @PutMapping
    public AjaxResult edit(@RequestBody CustomsInventoryItem item)
    {
        try { return success(inventoryService.update(item)); }
        catch (Exception e) { return error(e.getMessage()); }
    }

    @Log(title = "报关出入库清单导出", businessType = BusinessType.EXPORT)
    @PreAuthorize("@ss.hasPermi('customs:inventory:export')")
    @PostMapping("/export")
    public void export(@RequestBody(required = false) List<Long> ids, HttpServletResponse response) throws Exception
    {
        inventoryService.export(ids, response);
    }
}
