package com.ruoyi.system.mapper.operation.ebay;

import com.ruoyi.system.domain.operation.ebay.EbayWarehouseRentAggregate;
import java.util.List;
import org.apache.ibatis.annotations.Param;

public interface EbayWarehouseRentMapper
{
    List<EbayWarehouseRentAggregate> selectByKeys(
            @Param("keys") List<EbayWarehouseRentAggregate> keys);

    int deleteAll();

    int batchInsert(@Param("items") List<EbayWarehouseRentAggregate> items);

    int rebuildFromDetails(
            @Param("importBatchId") String importBatchId,
            @Param("sourceFileName") String sourceFileName,
            @Param("importedBy") String importedBy);
}
