package com.ruoyi.web.controller.sop.image;

import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.utils.SecurityUtils;
import com.ruoyi.system.service.ISysMenuService;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.util.StringUtils;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 为统一 Python 脚本工作台下发当前 ERP 用户可用的脚本权限与安全会话。
 *
 * 脚本注册表在 Python 端（页面/路由来源）；ERP 端仅通过 sys_menu 的 F 类型
 * 按钮权限控制可见性。这里查询「脚本菜单」下的全部脚本按钮 perms，
 * 再按当前登录用户的权限过滤后返回，工作台据此生成对应的组件与按钮。
 */
@Tag(name = "SOP-Python脚本工作台")
@RestController
@RequestMapping("/sop/python-tools")
public class PythonToolsSessionController extends BaseController
{
    private final ImageSopSessionService sessionService;
    private final ImageSopPythonProperties properties;
    private final ISysMenuService menuService;

    public PythonToolsSessionController(ImageSopSessionService sessionService,
            ImageSopPythonProperties properties, ISysMenuService menuService)
    {
        this.sessionService = sessionService;
        this.properties = properties;
        this.menuService = menuService;
    }

    @PreAuthorize("@ss.hasPermi('sop:scriptTools:view')")
    @PostMapping("/session")
    public AjaxResult createSession()
    {
        List<String> permissions = new ArrayList<>();
        for (String perm : menuService.selectScriptToolPerms())
        {
            if (StringUtils.hasText(perm) && SecurityUtils.hasPermi(perm))
            {
                permissions.add(perm);
            }
        }

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("workbenchUrl", properties.getWorkbenchUrl());
        result.put("permissions", permissions);
        result.put("workbenchSession", sessionService.issue(
                SecurityUtils.getUserId(), SecurityUtils.getUsername()).session());
        result.put("userId", SecurityUtils.getUserId());
        result.put("username", SecurityUtils.getUsername());
        return success(result);
    }
}
