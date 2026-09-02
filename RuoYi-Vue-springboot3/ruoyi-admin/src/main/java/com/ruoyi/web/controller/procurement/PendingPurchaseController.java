package com.ruoyi.web.controller.procurement;

import com.ruoyi.common.annotation.Log;
import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.core.page.TableDataInfo;
import com.ruoyi.common.enums.BusinessType;
import com.ruoyi.system.domain.procurement.PendingPurchase;
import com.ruoyi.system.domain.procurement.PendingPurchaseExportRequest;
import com.ruoyi.system.domain.procurement.PendingPurchaseSubmitRequest;
import com.ruoyi.system.service.procurement.PendingPurchaseService;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.validation.Valid;
import java.io.IOException;
import java.util.List;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@Tag(name = "采购中心-待采购")
@Validated
@RestController
@RequestMapping("/procurement/pending-purchase")
public class PendingPurchaseController extends BaseController
{
    private final PendingPurchaseService service;

    public PendingPurchaseController(PendingPurchaseService service)
    {
        this.service = service;
    }

    @PreAuthorize("@ss.hasPermi('procurement:pendingPurchase:list')")
    @GetMapping("/list")
    public TableDataInfo list(@RequestParam(required = false) String site,
                              @RequestParam(required = false) String sku,
                              @RequestParam(required = false) String status)
    {
        service.validateStatusFilter(status);
        startPage();
        List<PendingPurchase> rows = service.list(site, sku, status);
        return getDataTable(rows);
    }

    @Log(title = "待采购确认", businessType = BusinessType.INSERT)
    @PreAuthorize("@ss.hasPermi('procurement:pendingPurchase:add')")
    @PostMapping
    public AjaxResult submit(@Valid @RequestBody PendingPurchaseSubmitRequest request)
    {
        service.submit(request, getUsername());
        return success("已加入待采购清单");
    }

    @Log(title = "待采购导出并确认采购", businessType = BusinessType.EXPORT)
    @PreAuthorize("@ss.hasPermi('procurement:pendingPurchase:export')")
    @PostMapping("/export")
    public void export(@Valid @RequestBody PendingPurchaseExportRequest request,
                       HttpServletResponse response) throws IOException
    {
        service.exportAndMarkPurchased(request.getIds(), getUsername(), response);
    }
}
