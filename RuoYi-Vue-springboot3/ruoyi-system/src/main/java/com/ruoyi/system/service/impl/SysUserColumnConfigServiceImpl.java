package com.ruoyi.system.service.impl;

import com.ruoyi.system.domain.SysUserColumnConfig;
import com.ruoyi.system.mapper.SysUserColumnConfigMapper;
import com.ruoyi.system.service.ISysUserColumnConfigService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

@Service
public class SysUserColumnConfigServiceImpl implements ISysUserColumnConfigService
{
    @Autowired
    private SysUserColumnConfigMapper mapper;

    @Override
    public String getConfig(Long userId, String userName, String pageKey)
    {
        SysUserColumnConfig cfg = mapper.selectByUserAndPage(userId, pageKey);
        return cfg != null ? cfg.getConfigJson() : null;
    }

    @Override
    public void saveConfig(Long userId, String userName, String pageKey, String configJson)
    {
        SysUserColumnConfig cfg = mapper.selectByUserAndPage(userId, pageKey);
        if (cfg != null)
        {
            cfg.setConfigJson(configJson);
            mapper.update(cfg);
        }
        else
        {
            SysUserColumnConfig newCfg = new SysUserColumnConfig();
            newCfg.setUserId(userId); newCfg.setUserName(userName);
            newCfg.setPageKey(pageKey); newCfg.setConfigJson(configJson);
            mapper.insert(newCfg);
        }
    }
}
