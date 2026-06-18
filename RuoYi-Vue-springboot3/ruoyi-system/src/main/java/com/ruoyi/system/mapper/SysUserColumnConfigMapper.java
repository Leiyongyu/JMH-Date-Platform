package com.ruoyi.system.mapper;

import org.apache.ibatis.annotations.Param;
import com.ruoyi.system.domain.SysUserColumnConfig;

public interface SysUserColumnConfigMapper
{
    SysUserColumnConfig selectByUserPage(@Param("userId") Long userId, @Param("pageKey") String pageKey);

    int insertConfig(SysUserColumnConfig config);

    int updateConfig(SysUserColumnConfig config);
}
