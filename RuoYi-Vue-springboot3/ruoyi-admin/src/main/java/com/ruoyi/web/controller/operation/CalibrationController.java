package com.ruoyi.web.controller.operation;

import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.system.service.operation.sync.OperationCalibrationSyncService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.time.LocalDate;
import java.util.Map;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

@Tag(name = "数据校准")
@RestController
@RequestMapping("/operations/sync/calibration")
public class CalibrationController extends BaseController
{
    private final OperationCalibrationSyncService calibrationService;

    public CalibrationController(OperationCalibrationSyncService calibrationService)
    { this.calibrationService = calibrationService; }

    @PreAuthorize("@ss.hasRole('admin')")
    @PostMapping("/full")
    public AjaxResult runFull(
            @RequestParam @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate start,
            @RequestParam @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate end,
            @RequestParam(defaultValue = "true") boolean ebay,
            @RequestParam(defaultValue = "true") boolean amz,
            @RequestParam(defaultValue = "false") boolean inventoryPurchase,
            @RequestParam(defaultValue = "false") boolean goodcang)
    {
        Map<String, Object> result = calibrationService.runFullCalibration(start, end, ebay, amz, inventoryPurchase, goodcang);
        String status = (String) result.get("status");
        if ("FAILED".equals(status)) return error("数据校准全部失败");
        if ("PARTIAL_SUCCESS".equals(status))
            return AjaxResult.success("部分完成(" + result.get("successSteps") + "/" + result.get("totalSteps") + ")", result);
        return success(result);
    }
}
