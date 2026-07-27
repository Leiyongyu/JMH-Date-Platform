package com.ruoyi.system.mapper.operation.customs;

import com.ruoyi.system.domain.operation.customs.CustomsShipmentFeeImportLog;
import java.util.List;
import org.apache.ibatis.annotations.Param;

public interface CustomsShipmentFeeImportLogMapper
{
    int insert(CustomsShipmentFeeImportLog log);

    int updateResult(CustomsShipmentFeeImportLog log);

    List<CustomsShipmentFeeImportLog> selectList(
            @Param("businessType") String businessType,
            @Param("batchNo") String batchNo,
            @Param("orderSn") String orderSn,
            @Param("status") String status,
            @Param("operator") String operator,
            @Param("beginTime") String beginTime,
            @Param("endTime") String endTime);
}
