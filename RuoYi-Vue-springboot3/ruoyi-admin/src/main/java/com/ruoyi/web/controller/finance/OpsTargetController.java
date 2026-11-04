package com.ruoyi.web.controller.finance;

import com.ruoyi.common.annotation.Log;
import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.enums.BusinessType;
import com.ruoyi.common.utils.SecurityUtils;
import com.ruoyi.system.service.finance.PerformancePythonClient;
import java.util.Map;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

/** 财务中心「运营目标与人效」：部门年度目标、季度/月度分解与人效KPI，数据手工维护，存 Python 业务库。 */
@RestController
@RequestMapping("/finance/ops-target")
public class OpsTargetController extends BaseController
{
    private final PerformancePythonClient client;

    public OpsTargetController(PerformancePythonClient client) { this.client = client; }

    @PreAuthorize("@ss.hasPermi('finance:opsTarget:list')")
    @GetMapping("/report")
    public AjaxResult report(@RequestParam(required = false) Integer year,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId)
    {
        try { return success(client.opsTargetReport(year, requestId).get("data")); }
        catch (Exception e) { return error(e.getMessage()); }
    }

    /** body：{"values": {字段: 新值}}，只改传入的字段；返回修改后的整年数据。 */
    @Log(title = "运营目标与人效", businessType = BusinessType.UPDATE)
    @PreAuthorize("@ss.hasPermi('finance:opsTarget:list') and @ss.hasPermi('finance:opsTarget:edit')")
    @PutMapping("/rows/{year}/{deptCode}")
    public AjaxResult update(@PathVariable int year, @PathVariable String deptCode,
            @RequestBody Map<String, Object> body,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId)
    {
        @SuppressWarnings("unchecked")
        Map<String, Object> values = body == null || !(body.get("values") instanceof Map<?, ?> map)
                ? Map.of() : (Map<String, Object>) map;
        try
        {
            return success(client.updateOpsTarget(year, deptCode, values, SecurityUtils.getUsername(), requestId)
                    .get("data"));
        }
        catch (Exception e) { return error(e.getMessage()); }
    }
}
