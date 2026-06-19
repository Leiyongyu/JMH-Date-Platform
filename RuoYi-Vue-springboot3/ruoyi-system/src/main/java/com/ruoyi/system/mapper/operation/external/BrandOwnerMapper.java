package com.ruoyi.system.mapper.operation.external;

import java.util.List;

import org.apache.ibatis.annotations.Param;

import com.ruoyi.system.domain.operation.external.BrandOwner;

public interface BrandOwnerMapper
{
    List<BrandOwner> selectAll();
    int insert(BrandOwner entity);
    int update(BrandOwner entity);
    int deleteById(@Param("id") Integer id);
}
