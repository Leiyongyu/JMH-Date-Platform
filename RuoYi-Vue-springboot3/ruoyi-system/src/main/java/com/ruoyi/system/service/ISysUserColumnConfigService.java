package com.ruoyi.system.service;

public interface ISysUserColumnConfigService
{
    String selectConfigJson(Long userId, String pageKey);

    int saveConfigJson(Long userId, String userName, String pageKey, String configJson);
}
