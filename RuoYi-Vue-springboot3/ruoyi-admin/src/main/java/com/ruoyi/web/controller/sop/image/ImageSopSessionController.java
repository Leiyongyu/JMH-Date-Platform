package com.ruoyi.web.controller.sop.image;

import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.utils.SecurityUtils;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** ERP 图片SOP内嵌会话。 */
@Tag(name = "SOP-图片SOP")
@RestController
@RequestMapping("/sop/image-sop")
public class ImageSopSessionController extends BaseController
{
    private final ImageSopSessionService sessionService;

    public ImageSopSessionController(ImageSopSessionService sessionService)
    {
        this.sessionService = sessionService;
    }

    @PreAuthorize("@ss.hasPermi('sop:imageSop:use')")
    @PostMapping("/session")
    public AjaxResult createSession()
    {
        return success(sessionService.issue(
                SecurityUtils.getUserId(), SecurityUtils.getUsername(),
                java.util.Set.of(ImageSopSessionService.IMAGE_SOP_PERMISSION)).asMap());
    }
}
