package com.ruoyi.web.controller.operation;

import com.ruoyi.common.utils.spring.SpringUtils;
import com.ruoyi.system.service.operation.external.lingxing.LingxingGatewayService;
import com.ruoyi.system.service.operation.external.lingxing.LingxingShopSyncService;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import java.util.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.CommandLineRunner;
import org.springframework.stereotype.Component;

/** 启动时自动测试店铺同步，15秒后执行 */
@Component
public class ShopSyncTester implements CommandLineRunner
{
    private static final Logger LOG = LoggerFactory.getLogger(ShopSyncTester.class);

    @Override
    public void run(String... args)
    {
        new Thread(() -> {
            try { Thread.sleep(15000); } catch (Exception e) {}
            LOG.info("========== 店铺同步测试开始 ==========");
            try {
                LingxingGatewayService gw = SpringUtils.getBean(LingxingGatewayService.class);
                Map<String, Object> body = new LinkedHashMap<>();
                body.put("platform_code", Arrays.asList(10003, 10001));
                body.put("is_sync", 1);
                body.put("status", 1);
                body.put("offset", 0);
                body.put("length", 5);
                Map<String, Object> raw = gw.post("pb/mp/shop/v2/getSellerList", body);
                LOG.info("RAW API code={} msg={}", raw.get("code"), raw.get("msg"));
                Object d = raw.get("data");
                if (d instanceof List) {
                    LOG.info("RAW data type=List size={}", ((List<?>) d).size());
                    if (!((List<?>) d).isEmpty()) LOG.info("FIRST: {}", ((List<?>) d).get(0));
                } else if (d instanceof Map) {
                    Map<?,?> dm = (Map<?,?>) d;
                    LOG.info("RAW data type=Map keys={}", dm.keySet());
                    Object inner = dm.get("data");
                    if (inner instanceof List) {
                        LOG.info("RAW inner data size={}", ((List<?>) inner).size());
                        if (!((List<?>) inner).isEmpty()) LOG.info("FIRST: {}", ((List<?>) inner).get(0));
                    }
                } else {
                    LOG.info("RAW data type={}", d == null ? "null" : d.getClass().getName());
                }
                OperationSyncResult result = SpringUtils.getBean(LingxingShopSyncService.class).syncShops();
                LOG.info("SYNC result: status={} total={} success={} elapsed={}ms",
                        result.getStatus(), result.getTotalCount(), result.getSuccessCount(), result.getElapsedMs());
            } catch (Exception e) {
                LOG.error("测试失败: {}", e.getMessage(), e);
            }
            LOG.info("========== 店铺同步测试结束 ==========");
        }, "shop-sync-tester").start();
    }
}
