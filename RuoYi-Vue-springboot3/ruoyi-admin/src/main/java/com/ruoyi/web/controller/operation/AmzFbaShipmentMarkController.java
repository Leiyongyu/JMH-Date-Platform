package com.ruoyi.web.controller.operation;

import java.util.Map;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.system.domain.operation.external.AmzFbaShipmentMark;
import com.ruoyi.system.mapper.operation.external.AmzFbaShipmentMarkMapper;

@RestController
@RequestMapping("/operations/amz/fba-shipment/mark")
public class AmzFbaShipmentMarkController extends BaseController
{
    @Autowired
    private AmzFbaShipmentMarkMapper markMapper;

    /** 保存备注 */
    @PreAuthorize("@ss.hasPermi('operations:amzReplenishment:list')")
    @PostMapping("/remark")
    public AjaxResult saveRemark(@RequestBody Map<String, String> body)
    {
        AmzFbaShipmentMark mark = new AmzFbaShipmentMark();
        mark.setMsku(body.get("msku"));
        mark.setRemark(body.getOrDefault("remark", ""));
        AmzFbaShipmentMark existing = markMapper.selectByMsku(body.get("msku"));
        mark.setConfirmed(existing != null ? existing.getConfirmed() : 0);
        markMapper.upsert(mark);
        return success();
    }

    /** 确认已完结 */
    @PreAuthorize("@ss.hasPermi('operations:amzReplenishment:list')")
    @PostMapping("/confirm")
    public AjaxResult confirm(@RequestBody Map<String, String> body)
    {
        markMapper.confirm(body.get("msku"));
        return success();
    }
}
