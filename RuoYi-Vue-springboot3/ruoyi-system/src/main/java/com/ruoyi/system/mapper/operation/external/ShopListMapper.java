package com.ruoyi.system.mapper.operation.external;

import com.ruoyi.system.domain.operation.external.ShopList;
import org.apache.ibatis.annotations.Param;
import java.util.List;

/**
 * 多平台店铺 Mapper。
 *
 * @author JMH
 */
public interface ShopListMapper
{
    /** 按 platform_code + store_id 查一条 */
    ShopList selectByPlatformAndStore(@Param("platformCode") String platformCode,
                                      @Param("storeId") String storeId);

    /** 批量按 (platform_code, store_id) 查已有记录（用于同步去重） */
    List<ShopList> selectByKeys(@Param("keys") List<ShopListKey> keys);

    /** 批量插入 */
    int batchInsert(@Param("list") List<ShopList> list);

    /** 单条更新（按 id） */
    int updateById(ShopList shop);

    /** 按平台和状态查 id 列表（用于后续 Listing 同步） */
    List<String> selectSidsByPlatform(@Param("platformCode") String platformCode,
                                      @Param("status") Integer status);

    /** 按平台查去重店铺名称 */
    List<String> selectStoreNamesByPlatform(@Param("platformCode") String platformCode);

    /** 按平台和状态查店铺列表 */
    List<ShopList> selectByPlatformStatus(@Param("platformCode") String platformCode,
                                          @Param("status") Integer status);

    /** 内部类：联合键 */
    class ShopListKey
    {
        private String platformCode;
        private String storeId;

        public ShopListKey() {}
        public ShopListKey(String platformCode, String storeId)
        {
            this.platformCode = platformCode;
            this.storeId = storeId;
        }
        public String getPlatformCode() { return platformCode; }
        public void setPlatformCode(String platformCode) { this.platformCode = platformCode; }
        public String getStoreId() { return storeId; }
        public void setStoreId(String storeId) { this.storeId = storeId; }
    }
}
