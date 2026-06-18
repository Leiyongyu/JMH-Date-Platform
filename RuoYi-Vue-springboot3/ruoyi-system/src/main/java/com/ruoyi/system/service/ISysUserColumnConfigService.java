package com.ruoyi.system.service;

public interface ISysUserColumnConfigService
{
    String getConfig(Long userId, String userName, String pageKey);
    void saveConfig(Long userId, String userName, String pageKey, String configJson);
}
