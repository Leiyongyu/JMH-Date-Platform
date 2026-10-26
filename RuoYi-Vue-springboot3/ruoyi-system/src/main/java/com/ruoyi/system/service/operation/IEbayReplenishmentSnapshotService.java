package com.ruoyi.system.service.operation;

/**
 * 跟价仍使用的历史补货量计算。仅供内部同步任务调用，不再提供补货1.0页面接口。
 * 与Python补货2.0的计算、规则和刷新相互独立。
 */
public interface IEbayReplenishmentSnapshotService
{
    int refreshSnapshot();
}
