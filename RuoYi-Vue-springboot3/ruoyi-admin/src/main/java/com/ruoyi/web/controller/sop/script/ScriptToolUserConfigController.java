package com.ruoyi.web.controller.sop.script;

import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.utils.SecurityUtils;
import com.ruoyi.system.service.sop.AmazonImageUploadUserConfigService;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** ERP当前用户的紫鸟运行配置。密码不落库，也不在响应中返回。 */
@Tag(name = "SOP-脚本菜单-主图上传用户配置")
@RestController
@RequestMapping("/sop/script-tools/amazon-image-upload/config")
public class ScriptToolUserConfigController extends BaseController
{
    private final AmazonImageUploadUserConfigService configService;

    public ScriptToolUserConfigController(AmazonImageUploadUserConfigService configService)
    {
        this.configService = configService;
    }

    @PreAuthorize("@ss.hasPermi('sop:amazonImageUpload:use')")
    @GetMapping
    public AjaxResult getConfig()
    {
        return success(configService.getConfigStatus(SecurityUtils.getUserId()));
    }

    @PreAuthorize("@ss.hasPermi('sop:amazonImageUpload:use')")
    @PutMapping
    public AjaxResult saveConfig(@RequestBody SaveConfigRequest request)
    {
        try
        {
            configService.saveConfig(
                    SecurityUtils.getUserId(),
                    SecurityUtils.getUsername(),
                    request.getCompanyName(),
                    request.getAccountName(),
                    request.getClientPath(),
                    request.getPassword());
            return success(configService.getConfigStatus(SecurityUtils.getUserId()));
        }
        catch (IllegalArgumentException e)
        {
            return error(e.getMessage());
        }
    }

    @PreAuthorize("@ss.hasPermi('sop:amazonImageUpload:use')")
    @DeleteMapping("/password")
    public AjaxResult clearPassword()
    {
        configService.clearPassword(SecurityUtils.getUserId());
        return success(configService.getConfigStatus(SecurityUtils.getUserId()));
    }

    public static class SaveConfigRequest
    {
        private String companyName;
        private String accountName;
        private String clientPath;
        private String password;

        public String getCompanyName()
        {
            return companyName;
        }

        public void setCompanyName(String companyName)
        {
            this.companyName = companyName;
        }

        public String getAccountName()
        {
            return accountName;
        }

        public void setAccountName(String accountName)
        {
            this.accountName = accountName;
        }

        public String getClientPath()
        {
            return clientPath;
        }

        public void setClientPath(String clientPath)
        {
            this.clientPath = clientPath;
        }

        public String getPassword()
        {
            return password;
        }

        public void setPassword(String password)
        {
            this.password = password;
        }
    }
}
