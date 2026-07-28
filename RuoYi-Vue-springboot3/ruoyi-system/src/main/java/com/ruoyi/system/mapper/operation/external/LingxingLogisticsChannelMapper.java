package com.ruoyi.system.mapper.operation.external;

import com.ruoyi.system.domain.operation.external.LingxingLogisticsChannel;
import java.util.List;
import org.apache.ibatis.annotations.Param;

public interface LingxingLogisticsChannelMapper
{
    int deleteAll();

    int batchInsert(@Param("list") List<LingxingLogisticsChannel> list);

    int countAll();

    int countByIdAndProvider(
            @Param("channelId") Long channelId,
            @Param("providerId") Long providerId);
}
