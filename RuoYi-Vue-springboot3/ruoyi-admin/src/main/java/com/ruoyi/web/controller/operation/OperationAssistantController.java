package com.ruoyi.web.controller.operation;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.ruoyi.common.core.domain.AjaxResult;

import io.swagger.v3.oas.annotations.tags.Tag;

/**
 * 运营助手统一鉴权入口。
 *
 * Nginx auth_request 会把若依 Admin-Token Cookie 转换成 Authorization 请求头后调用本接口。
 * 业务服务无需再维护独立账号库，也无需接触若依 JWT。
 */
@Tag(name = "运营助手")
@RestController
@RequestMapping("/operations/assistant")
public class OperationAssistantController
{
    @PreAuthorize("@ss.hasPermi('operations:assistant:view')")
    @GetMapping("/auth-check")
    public AjaxResult authCheck()
    {
        return AjaxResult.success("authenticated");
    }
}
