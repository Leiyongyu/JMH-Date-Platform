package com.ruoyi.web.controller.operation;

import com.ruoyi.common.annotation.Log;
import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.core.page.TableDataInfo;
import com.ruoyi.common.enums.BusinessType;
import com.ruoyi.system.service.operation.customs.CustomsPackingInfoImportService;
import com.ruoyi.system.service.operation.customs.CustomsShipmentFeeImportService;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@Tag(name = "报关管理-发货单费用")
@RestController
@RequestMapping("/operations/customs/shipment-fee")
public class CustomsShipmentFeeController extends BaseController
{
    private final CustomsShipmentFeeImportService importService;
    private final CustomsPackingInfoImportService packingInfoImportService;

    public CustomsShipmentFeeController(
            CustomsShipmentFeeImportService importService,
            CustomsPackingInfoImportService packingInfoImportService)
    {
        this.importService = importService;
        this.packingInfoImportService = packingInfoImportService;
    }

    @PreAuthorize("@ss.hasPermi('customs:shipmentFee:list')")
    @GetMapping("/batches")
    public TableDataInfo batches(
            @RequestParam(required = false) String businessType,
            @RequestParam(required = false) String batchNo,
            @RequestParam(required = false) String status,
            @RequestParam(required = false) String operator)
    {
        startPage();
        return getDataTable(importService.listBatches(
                businessType, batchNo, status, operator));
    }

    @PreAuthorize("@ss.hasPermi('customs:shipmentFee:list')")
    @GetMapping("/logs")
    public TableDataInfo logs(
            @RequestParam(required = false) String businessType,
            @RequestParam(required = false) String batchNo,
            @RequestParam(required = false) String orderSn,
            @RequestParam(required = false) String status,
            @RequestParam(required = false) String operator,
            @RequestParam(required = false) String beginTime,
            @RequestParam(required = false) String endTime)
    {
        startPage();
        return getDataTable(importService.listLogs(
                businessType, batchNo, orderSn, status, operator, beginTime, endTime));
    }

    @Log(title = "发货单费用明细批量上传", businessType = BusinessType.IMPORT)
    @PreAuthorize("@ss.hasPermi('customs:shipmentFee:import')")
    @PostMapping("/import")
    public AjaxResult importFile(@RequestParam("file") MultipartFile file)
    {
        try
        {
            return success(importService.importFile(file, getUsername()));
        }
        catch (Exception e)
        {
            return error(e.getMessage());
        }
    }

    @Log(title = "装箱信息批量保存到领星ERP", businessType = BusinessType.IMPORT)
    @PreAuthorize("@ss.hasPermi('customs:shipmentFee:import')")
    @PostMapping("/packing/import")
    public AjaxResult importPackingInfo(@RequestParam("file") MultipartFile file)
    {
        try
        {
            return success(packingInfoImportService.importFile(file, getUsername()));
        }
        catch (Exception e)
        {
            return error(e.getMessage());
        }
    }
}
