package com.ruoyi.web.controller.operation;

import com.ruoyi.common.annotation.Log;
import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.core.page.TableDataInfo;
import com.ruoyi.common.enums.BusinessType;
import com.ruoyi.common.utils.SecurityUtils;
import com.ruoyi.system.domain.operation.external.ShopList;
import com.ruoyi.system.mapper.operation.external.ShopListMapper;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.time.LocalDate;
import java.util.List;
import java.util.Map;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.util.StringUtils;
import org.springframework.web.bind.annotation.*;

/**
 * 店铺管理：控制每个店铺是否继续向领星拉取数据。停止拉取只影响以后的拉取，已入库的历史数据不动；
 * 按月拉取的任务对停止日期之前开始的月份仍会拉取。领星已不再返回的店铺由店铺同步自动标记。
 */
@Tag(name = "店铺管理")
@RestController
@RequestMapping("/operations/sync/shop")
public class ShopPullController extends BaseController
{
    private final ShopListMapper shopMapper;

    public ShopPullController(ShopListMapper shopMapper) { this.shopMapper = shopMapper; }

    @PreAuthorize("@ss.hasPermi('operations:shopPull:list')")
    @GetMapping("/list")
    public TableDataInfo list(@RequestParam(required = false) String platformCode,
                              @RequestParam(required = false) String keyword,
                              @RequestParam(required = false) Integer pullEnabled,
                              @RequestParam(required = false) Integer lingxingPresent)
    {
        startPage();
        List<ShopList> rows = shopMapper.selectForManage(platformCode,
                StringUtils.hasText(keyword) ? keyword.trim() : null, pullEnabled, lingxingPresent);
        return getDataTable(rows);
    }

    /** body：{pullEnabled: 0|1, pullStopReason, pullStopDate: "yyyy-MM-dd"}；停止拉取时原因和日期必填，恢复时清空。 */
    @Log(title = "店铺管理-拉取开关", businessType = BusinessType.UPDATE)
    @PreAuthorize("@ss.hasPermi('operations:shopPull:list') and @ss.hasPermi('operations:shopPull:edit')")
    @PutMapping("/{id}/pull")
    public AjaxResult updatePull(@PathVariable Long id, @RequestBody Map<String, Object> body)
    {
        ShopList update = buildUpdate(id, body, SecurityUtils.getUsername());
        if (shopMapper.updatePullControl(update) == 0)
            return error("店铺不存在");
        return success();
    }

    static ShopList buildUpdate(Long id, Map<String, Object> body, String operator)
    {
        Object flag = body == null ? null : body.get("pullEnabled");
        if (!(flag instanceof Number number) || (number.intValue() != 0 && number.intValue() != 1))
            throw new IllegalArgumentException("pullEnabled 只能是 0 或 1");
        ShopList update = new ShopList();
        update.setId(id);
        update.setPullEnabled(number.intValue());
        update.setPullUpdatedBy(operator);
        if (number.intValue() == 0)
        {
            String reason = body.get("pullStopReason") == null ? "" : String.valueOf(body.get("pullStopReason")).trim();
            String date = body.get("pullStopDate") == null ? "" : String.valueOf(body.get("pullStopDate")).trim();
            if (!StringUtils.hasText(reason))
                throw new IllegalArgumentException("停止拉取需要填写原因");
            if (reason.length() > 200)
                throw new IllegalArgumentException("原因最多 200 字");
            if (!StringUtils.hasText(date))
                throw new IllegalArgumentException("停止拉取需要选择生效日期");
            update.setPullStopReason(reason);
            update.setPullStopDate(LocalDate.parse(date));
        }
        return update;
    }
}
