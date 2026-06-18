package com.ruoyi.web.controller.operation;

import java.util.List;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import com.ruoyi.common.annotation.Log;
import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.page.TableDataInfo;
import com.ruoyi.common.enums.BusinessType;
import com.ruoyi.common.utils.poi.ExcelUtil;
import com.ruoyi.system.domain.operation.EbayReplenishmentSnapshot;
import com.ruoyi.system.service.operation.IEbayReplenishmentSnapshotService;

@RestController
@RequestMapping("/operations/ebay/replenishment")
public class EbayReplenishmentController extends BaseController
{
    @Autowired
    private IEbayReplenishmentSnapshotService snapshotService;

    @PreAuthorize("@ss.hasPermi('operations:ebayReplenishment:list')")
    @GetMapping("/list")
    public TableDataInfo list(EbayReplenishmentSnapshot snapshot)
    {
        startPage();
        List<EbayReplenishmentSnapshot> list = snapshotService.selectEbayReplenishmentSnapshotList(snapshot);
        return getDataTable(list);
    }

    @Log(title = "eBay补货", businessType = BusinessType.EXPORT)
    @PreAuthorize("@ss.hasPermi('operations:ebayReplenishment:export')")
    @PostMapping("/export")
    public void export(HttpServletResponse response, EbayReplenishmentSnapshot snapshot)
    {
        List<EbayReplenishmentSnapshot> list = snapshotService.selectEbayReplenishmentSnapshotList(snapshot);
        ExcelUtil<EbayReplenishmentSnapshot> util = new ExcelUtil<>(EbayReplenishmentSnapshot.class);
        util.exportExcel(response, list, "eBay补货数据");
    }
}
