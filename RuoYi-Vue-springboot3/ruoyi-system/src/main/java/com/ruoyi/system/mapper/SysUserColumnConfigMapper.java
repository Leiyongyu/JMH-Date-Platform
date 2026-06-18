package com.ruoyi.system.mapper;

import com.ruoyi.system.domain.SysUserColumnConfig;
import org.apache.ibatis.annotations.Param;

public interface SysUserColumnConfigMapper
{
    SysUserColumnConfig selectByUserAndPage(@Param("userId") Long userId, @Param("pageKey") String pageKey);
    int insert(SysUserColumnConfig config);
    int update(SysUserColumnConfig config);
}
