package com.ruoyi.system.mapper.sop;

import com.ruoyi.system.domain.sop.AmazonImageUploadUserConfig;
import org.apache.ibatis.annotations.Param;

public interface AmazonImageUploadUserConfigMapper
{
    AmazonImageUploadUserConfig selectByUserId(@Param("userId") Long userId);

    int insertConfig(AmazonImageUploadUserConfig config);

    int updateConfig(AmazonImageUploadUserConfig config);
}
