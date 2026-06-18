package com.ruoyi.system.service.impl;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;
import com.ruoyi.system.domain.SysUserColumnConfig;
import com.ruoyi.system.mapper.SysUserColumnConfigMapper;
import com.ruoyi.system.service.ISysUserColumnConfigService;

@Service
public class SysUserColumnConfigServiceImpl implements ISysUserColumnConfigService
{
    @Autowired
    private SysUserColumnConfigMapper columnConfigMapper;

    @Override
    public String selectConfigJson(Long userId, String pageKey)
    {
        if (userId == null || !StringUtils.hasText(pageKey))
        {
            return null;
        }
        SysUserColumnConfig config = columnConfigMapper.selectByUserPage(userId, pageKey);
        return config != null ? config.getConfigJson() : null;
    }

    @Override
    public int saveConfigJson(Long userId, String userName, String pageKey, String configJson)
    {
        if (userId == null || !StringUtils.hasText(pageKey))
        {
            throw new IllegalArgumentException("pageKey is required");
        }
        SysUserColumnConfig config = columnConfigMapper.selectByUserPage(userId, pageKey);
        if (config == null)
        {
            config = new SysUserColumnConfig();
            config.setUserId(userId);
            config.setUserName(userName);
            config.setPageKey(pageKey);
            config.setConfigJson(configJson);
            config.setCreateBy(userName);
            return columnConfigMapper.insertConfig(config);
        }
        config.setUserName(userName);
        config.setConfigJson(configJson);
        config.setUpdateBy(userName);
        return columnConfigMapper.updateConfig(config);
    }
}
