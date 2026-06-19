package com.ruoyi.web.controller.operation;

import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.utils.spring.SpringUtils;
import com.ruoyi.system.service.operation.external.lingxing.*;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import java.util.*;
import org.springframework.web.bind.annotation.*;

/** 开发期调试接口 —— 直接调用同步服务并打印原始响应 */
@RestController
@RequestMapping("/operations/debug")
public class DebugSyncController extends BaseController
{
    /** 直接调网关手动请求，返回原始 JSON */
    @PostMapping("/raw")
    public AjaxResult raw(@RequestBody Map<String, Object> body) {
        try {
            String path = (String) body.remove("_path");
            LingxingGatewayService gw = SpringUtils.getBean(LingxingGatewayService.class);
            Map<String, Object> resp = gw.post(path, body);
            return success(resp);
        } catch (Exception e) {
            return error(e.getMessage());
        }
    }

    /** 测试店铺同步，打印每一步 */
    @PostMapping("/shop-sync")
    public AjaxResult testShopSync() {
        Map<String, Object> debug = new LinkedHashMap<>();
        try {
            // 1. 测试 API 调用
            LingxingGatewayService gw = SpringUtils.getBean(LingxingGatewayService.class);
            Map<String, Object> reqBody = new LinkedHashMap<>();
            reqBody.put("platform_code", Arrays.asList(10003, 10001));
            reqBody.put("is_sync", 1);
            reqBody.put("status", 1);
            reqBody.put("offset", 0);
            reqBody.put("length", 5);
            Map<String, Object> rawResp = gw.post("pb/mp/shop/v2/getSellerList", reqBody);
            debug.put("raw_api_response_code", rawResp.get("code"));
            debug.put("raw_api_response_msg", rawResp.get("msg"));
            Object data = rawResp.get("data");
            if (data instanceof List) {
                debug.put("data_type", "List");
                debug.put("data_size", ((List<?>) data).size());
                if (!((List<?>) data).isEmpty()) {
                    debug.put("first_item", ((List<?>) data).get(0));
                }
            } else if (data instanceof Map) {
                Map<?,?> dm = (Map<?,?>) data;
                debug.put("data_type", "Map");
                debug.put("data_keys", dm.keySet());
                // 可能是分页结构 {total, data: [...]}
                Object inner = dm.get("data");
                if (inner instanceof List) {
                    debug.put("inner_data_size", ((List<?>) inner).size());
                    if (!((List<?>) inner).isEmpty()) debug.put("first_item", ((List<?>) inner).get(0));
                }
            } else {
                debug.put("data_type", data == null ? "null" : data.getClass().getName());
            }

            // 2. 测试完整同步
            OperationSyncResult result = SpringUtils.getBean(LingxingShopSyncService.class).syncShops();
            debug.put("sync_result_status", result.getStatus());
            debug.put("sync_result_total", result.getTotalCount());
            debug.put("sync_result_success", result.getSuccessCount());
            debug.put("sync_result_elapsed_ms", result.getElapsedMs());
        } catch (Exception e) {
            debug.put("error", e.getMessage());
            debug.put("error_type", e.getClass().getName());
        }
        return success(debug);
    }
}
