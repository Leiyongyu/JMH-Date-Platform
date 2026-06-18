package com.ruoyi.web.controller.operation;

import java.util.List;

import jakarta.servlet.http.HttpServletResponse;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import com.ruoyi.common.annotation.Log;
import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.core.page.TableDataInfo;
import com.ruoyi.common.enums.BusinessType;
import com.ruoyi.common.utils.poi.ExcelUtil;
import java.math.BigDecimal;
import java.util.Map;

import com.ruoyi.system.domain.operation.AmzReplenishmentSnapshot;
import com.ruoyi.system.domain.operation.EbayReplenishmentSearchRequest;
import com.ruoyi.system.domain.operation.ExportRequest;
import com.ruoyi.system.domain.operation.external.AmzReplenishmentOverride;
import com.ruoyi.system.mapper.operation.external.AmzReplenishmentOverrideMapper;
import com.ruoyi.system.service.operation.IAmzReplenishmentSnapshotService;
import com.ruoyi.system.service.operation.UnifiedExportService;
import com.github.pagehelper.PageHelper;

@RestController
@RequestMapping("/operations/amz/replenishment")
public class AmzReplenishmentController extends BaseController
{
    @Autowired
    private IAmzReplenishmentSnapshotService snapshotService;
    @Autowired
    private UnifiedExportService exportService;
    @Autowired
    private AmzReplenishmentOverrideMapper overrideMapper;

    // ====== 基础列表 ======
    @PreAuthorize("@ss.hasPermi('operations:amzReplenishment:list')")
    @GetMapping("/list")
    public TableDataInfo list(AmzReplenishmentSnapshot snapshot)
    {
        startPage();
        return getDataTable(snapshotService.selectAmzReplenishmentSnapshotList(snapshot));
    }

    // ====== 增强搜索 ======
    @PreAuthorize("@ss.hasPermi('operations:amzReplenishment:list')")
    @PostMapping("/search")
    public TableDataInfo search(@RequestBody EbayReplenishmentSearchRequest req)
    {
        PageHelper.startPage(req.getPageNum() != null ? req.getPageNum() : 1,
                             req.getPageSize() != null ? req.getPageSize() : 20);
        return getDataTable(snapshotService.search(req));
    }

    @PreAuthorize("@ss.hasPermi('operations:amzReplenishment:list')")
    @GetMapping("/distinct-values")
    public AjaxResult distinctValues(@RequestParam String field, @RequestParam(required = false) String keyword)
    {
        return AjaxResult.success(snapshotService.distinctValues(field, keyword));
    }

    // ====== 刷新 ======
    @Log(title = "Amazon补货", businessType = BusinessType.OTHER)
    @PreAuthorize("@ss.hasPermi('operations:amzReplenishment:list')")
    @PostMapping("/refresh")
    public AjaxResult refresh()
    {
        snapshotService.refreshSnapshot();
        return success();
    }

    // ====== 导出 ======
    @Log(title = "Amazon补货", businessType = BusinessType.EXPORT)
    @PreAuthorize("@ss.hasPermi('operations:amzReplenishment:export')")
    @PostMapping("/export")
    public void export(@RequestBody ExportRequest req, HttpServletResponse response) throws Exception
    {
        exportService.exportAmzReplenishment(req, response);
    }

    /** 保存人工覆盖：产品分类/已采购数量 */
    @Log(title = "AMZ补货-人工覆盖", businessType = BusinessType.UPDATE)
    @PreAuthorize("@ss.hasPermi('operations:amzReplenishment:list')")
    @PostMapping("/override")
    public AjaxResult saveOverride(@RequestBody Map<String, Object> body)
    {
        String sid = body.get("sid") != null ? String.valueOf(body.get("sid")) : null;
        String sellerSku = (String) body.get("sellerSku");
        if (sid == null || sellerSku == null) return error("sid和sellerSku必填");
        AmzReplenishmentOverride ov = new AmzReplenishmentOverride();
        ov.setSid(sid);
        ov.setSellerSku(sellerSku);
        if (body.containsKey("productCategory"))
            ov.setProductCategory((String) body.get("productCategory"));
        if (body.containsKey("manualPurchasedQty")) {
            Object v = body.get("manualPurchasedQty");
            ov.setManualPurchasedQty(v != null && !"".equals(v) ? new BigDecimal(String.valueOf(v)) : null);
        }
        overrideMapper.upsert(ov);
        return success();
    }
}
