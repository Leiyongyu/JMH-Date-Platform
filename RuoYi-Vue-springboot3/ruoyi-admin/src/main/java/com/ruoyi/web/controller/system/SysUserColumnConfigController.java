package com.ruoyi.web.controller.system;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.utils.SecurityUtils;
import com.ruoyi.system.service.ISysUserColumnConfigService;

@RestController
@RequestMapping("/system/user-column-config")
public class SysUserColumnConfigController extends BaseController
{
    @Autowired
    private ISysUserColumnConfigService columnConfigService;

    @GetMapping
    public AjaxResult getConfig(@RequestParam String pageKey)
    {
        String configJson = columnConfigService.selectConfigJson(SecurityUtils.getUserId(), pageKey);
        return success(configJson);
    }

    @PostMapping
    public AjaxResult saveConfig(@RequestParam(required = false) String pageKey, @RequestBody(required = false) SaveRequest request)
    {
        String actualPageKey = pageKey;
        String configJson = null;
        if (request != null)
        {
            if (actualPageKey == null || actualPageKey.isEmpty())
            {
                actualPageKey = request.getPageKey();
            }
            configJson = request.getConfigJson();
        }
        columnConfigService.saveConfigJson(
                SecurityUtils.getUserId(),
                SecurityUtils.getUsername(),
                actualPageKey,
                configJson);
        return success();
    }

    public static class SaveRequest
    {
        private String pageKey;
        private String configJson;

        public String getPageKey()
        {
            return pageKey;
        }

        public void setPageKey(String pageKey)
        {
            this.pageKey = pageKey;
        }

        public String getConfigJson()
        {
            return configJson;
        }

        public void setConfigJson(String configJson)
        {
            this.configJson = configJson;
        }
    }
}
