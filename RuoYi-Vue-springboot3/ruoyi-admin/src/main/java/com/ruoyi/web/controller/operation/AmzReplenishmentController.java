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
import com.ruoyi.system.domain.operation.AmzReplenishmentSnapshot;
import com.ruoyi.system.service.operation.IAmzReplenishmentSnapshotService;

@RestController
@RequestMapping("/operations/amz/replenishment")
public class AmzReplenishmentController extends BaseController
{
    @Autowired
    private IAmzReplenishmentSnapshotService snapshotService;

    @PreAuthorize("@ss.hasPermi('operations:amzReplenishment:list')")
    @GetMapping("/list")
    public TableDataInfo list(AmzReplenishmentSnapshot snapshot)
    {
        startPage();
        List<AmzReplenishmentSnapshot> list = snapshotService.selectAmzReplenishmentSnapshotList(snapshot);
        return getDataTable(list);
    }

    @Log(title = "Amazon补货", businessType = BusinessType.EXPORT)
    @PreAuthorize("@ss.hasPermi('operations:amzReplenishment:export')")
    @PostMapping("/export")
    public void export(HttpServletResponse response, AmzReplenishmentSnapshot snapshot)
    {
        List<AmzReplenishmentSnapshot> list = snapshotService.selectAmzReplenishmentSnapshotList(snapshot);
        ExcelUtil<AmzReplenishmentSnapshot> util = new ExcelUtil<>(AmzReplenishmentSnapshot.class);
        util.exportExcel(response, list, "Amazon补货数据");
    }
}
