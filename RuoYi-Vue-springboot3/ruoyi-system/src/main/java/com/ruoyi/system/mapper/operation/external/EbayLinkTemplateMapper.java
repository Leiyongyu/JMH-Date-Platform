package com.ruoyi.system.mapper.operation.external;

import java.util.List;

import org.apache.ibatis.annotations.Param;

import com.ruoyi.system.domain.operation.external.EbayLinkTemplate;

public interface EbayLinkTemplateMapper
{
    List<EbayLinkTemplate> selectAll();
    EbayLinkTemplate selectBySite(@Param("site") String site);
    int upsert(EbayLinkTemplate entity);
}
