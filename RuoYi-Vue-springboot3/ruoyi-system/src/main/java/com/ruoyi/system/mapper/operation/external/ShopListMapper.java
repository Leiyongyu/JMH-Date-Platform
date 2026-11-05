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

    /** 按平台和状态查要向领星拉取的 sid（排除店铺管理里停止拉取、以及领星已移除的店铺） */
    List<String> selectSidsByPlatform(@Param("platformCode") String platformCode,
                                      @Param("status") Integer status);

    /** 按平台查去重店铺名称 */
    List<String> selectStoreNamesByPlatform(@Param("platformCode") String platformCode);

    /** 按平台和状态查店铺列表 */
    List<ShopList> selectByPlatformStatus(@Param("platformCode") String platformCode,
                                          @Param("status") Integer status);

    /** 按平台和店铺名称精确匹配有效店铺，用于外部接口SID解析。 */
    List<ShopList> selectByStoreName(@Param("platformCode") String platformCode,
                                     @Param("storeName") String storeName,
                                     @Param("status") Integer status);

    /** 一次完整同步后，按领星本次返回的店铺标记 lingxing_present / lingxing_last_seen_at */
    int markLingxingPresence(@Param("platformCode") String platformCode, @Param("keys") List<ShopListKey> keys);

    /** 当前标记为「领星仍存在」的店铺数（用于判断本次同步结果是否异常） */
    int countPresentByPlatform(@Param("platformCode") String platformCode);

    /** 店铺管理页面：按平台、名称/sid、拉取开关、领星状态筛选 */
    List<ShopList> selectForManage(@Param("platformCode") String platformCode, @Param("keyword") String keyword,
                                   @Param("pullEnabled") Integer pullEnabled,
                                   @Param("lingxingPresent") Integer lingxingPresent);

    /** 店铺管理页面：修改拉取开关、原因与停止日期 */
    int updatePullControl(ShopList shop);

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
