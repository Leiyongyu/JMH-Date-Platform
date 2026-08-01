package com.ruoyi.web.controller.operation;

import com.ruoyi.common.annotation.Log;
import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.core.page.TableDataInfo;
import com.ruoyi.common.enums.BusinessType;
import com.ruoyi.system.service.operation.customs.CustomsPackingInfoImportService;
import com.ruoyi.system.service.operation.customs.CustomsPackingSubmissionService;
import com.ruoyi.system.service.operation.customs.CustomsShipmentFeeImportService;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
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
    private final CustomsPackingSubmissionService packingSubmissionService;

    public CustomsShipmentFeeController(
            CustomsShipmentFeeImportService importService,
            CustomsPackingInfoImportService packingInfoImportService,
            CustomsPackingSubmissionService packingSubmissionService)
    {
        this.importService = importService;
        this.packingInfoImportService = packingInfoImportService;
        this.packingSubmissionService = packingSubmissionService;
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

    /** 聚合历史保存成功日志，按STA任务展示待提交及提交状态。 */
    @PreAuthorize("@ss.hasPermi('customs:shipmentFee:list')")
    @GetMapping("/packing/submissions")
    public TableDataInfo packingSubmissions(
            @RequestParam(required = false) String inboundPlanId,
            @RequestParam(required = false) String status)
    {
        startPage();
        return getDataTable(
                packingSubmissionService.list(inboundPlanId, status));
    }

    @PreAuthorize("@ss.hasPermi('customs:shipmentFee:list')")
    @GetMapping("/packing/submissions/{id}")
    public AjaxResult packingSubmission(@PathVariable Long id)
    {
        try
        {
            return success(packingSubmissionService.get(id));
        }
        catch (Exception e)
        {
            return error(e.getMessage());
        }
    }

    @Log(title = "提交STA装箱信息", businessType = BusinessType.UPDATE)
    @PreAuthorize("@ss.hasPermi('customs:packingSubmission:submit')")
    @PostMapping("/packing/submissions/submit")
    public AjaxResult submitPacking(@RequestBody PackingSubmitRequest request)
    {
        try
        {
            if (request == null)
                return error("请求参数不能为空");
            return success(packingSubmissionService.submit(
                    request.getInboundPlanId(), getUsername()));
        }
        catch (Exception e)
        {
            return error(e.getMessage());
        }
    }

    @Log(title = "查询STA装箱提交状态", businessType = BusinessType.OTHER)
    @PreAuthorize("@ss.hasPermi('customs:packingSubmission:submit')")
    @PostMapping("/packing/submissions/{id}/refresh")
    public AjaxResult refreshPackingSubmission(@PathVariable Long id)
    {
        try
        {
            return success(packingSubmissionService.refreshStatus(id));
        }
        catch (Exception e)
        {
            return error(e.getMessage());
        }
    }

    public static class PackingSubmitRequest
    {
        private String inboundPlanId;

        public String getInboundPlanId() { return inboundPlanId; }
        public void setInboundPlanId(String inboundPlanId)
        {
            this.inboundPlanId = inboundPlanId;
        }
    }
}
