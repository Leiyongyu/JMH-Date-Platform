package com.ruoyi.system.mapper.operation.customs;

import com.ruoyi.system.domain.operation.customs.CustomsShipmentFeeImportBatch;
import java.util.List;
import org.apache.ibatis.annotations.Param;

public interface CustomsShipmentFeeImportBatchMapper
{
    int insert(CustomsShipmentFeeImportBatch batch);

    int updateResult(CustomsShipmentFeeImportBatch batch);

    List<CustomsShipmentFeeImportBatch> selectList(
            @Param("businessType") String businessType,
            @Param("batchNo") String batchNo,
            @Param("status") String status,
            @Param("operator") String operator);
}
