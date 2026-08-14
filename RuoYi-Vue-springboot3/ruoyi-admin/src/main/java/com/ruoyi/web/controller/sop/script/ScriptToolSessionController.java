package com.ruoyi.web.controller.sop.script;

import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.utils.SecurityUtils;
import com.ruoyi.system.service.sop.AmazonImageUploadUserConfigService;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** ERP脚本菜单的Amazon主图上传安全会话。 */
@Tag(name = "SOP-脚本菜单-主图上传")
@RestController
@RequestMapping("/sop/script-tools/amazon-image-upload")
public class ScriptToolSessionController extends BaseController
{
    private final ScriptToolSessionService sessionService;
    private final AmazonImageUploadUserConfigService configService;

    public ScriptToolSessionController(ScriptToolSessionService sessionService,
            AmazonImageUploadUserConfigService configService)
    {
        this.sessionService = sessionService;
        this.configService = configService;
    }

    @PreAuthorize("@ss.hasPermi('sop:amazonImageUpload:use')")
    @PostMapping("/session")
    public AjaxResult createSession()
    {
        try
        {
            configService.requireReady(SecurityUtils.getUserId());
        }
        catch (IllegalStateException e)
        {
            return error(e.getMessage());
        }
        return success(sessionService.issue(
                SecurityUtils.getUserId(), SecurityUtils.getUsername()).asMap());
    }
}
