package com.ruoyi.web.controller.system;

import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.utils.SecurityUtils;
import com.ruoyi.system.service.ISysUserColumnConfigService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/system/user-column-config")
public class SysUserColumnConfigController extends BaseController
{
    @Autowired
    private ISysUserColumnConfigService configService;

    @GetMapping
    public AjaxResult get(@RequestParam String pageKey)
    {
        Long userId = SecurityUtils.getUserId();
        String userName = SecurityUtils.getUsername();
        String config = configService.getConfig(userId, userName, pageKey);
        return success().put("data", config);
    }

    @PostMapping
    public AjaxResult save(@RequestParam String pageKey, @RequestBody String configJson)
    {
        Long userId = SecurityUtils.getUserId();
        String userName = SecurityUtils.getUsername();
        configService.saveConfig(userId, userName, pageKey, configJson);
        return success();
    }
}
