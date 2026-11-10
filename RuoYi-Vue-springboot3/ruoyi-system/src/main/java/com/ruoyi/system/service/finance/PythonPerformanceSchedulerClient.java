package com.ruoyi.system.service.finance;

import com.ruoyi.system.service.python.PythonHttpSupport;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

/** 调用仅供后端使用的Python绩效ETL任务接口。 */
@Service
public class PythonPerformanceSchedulerClient extends PythonHttpSupport
{
    private static final String TASK_PREFIX =
            "/api/v1/internal/scheduler/tasks/";
    private static final String PERFORMANCE_TASK =
            "amz_monthly_order_profit_sync";
    private static final String CLEARANCE_TASK =
            "amz_fba_inventory_snapshot_sync";
    private static final String INVENTORY_REPORT_SOURCE_TASK =
            "monthly_inventory_report_source_sync";
    private static final String INVENTORY_REPORT_SALES_VOLUME_TASK =
            "monthly_inventory_report_sales_volume_sync";
    private static final String INVENTORY_REPORT_OPENING_INVENTORY_TASK =
            "monthly_inventory_report_opening_inventory_fill";
    private static final String INVENTORY_REPORT_SALES_SNAPSHOT_REFRESH_TASK =
            "monthly_inventory_report_sales_snapshot_refresh";
    private static final String CURRENCY_MONTH_TASK =
            "currency_month_sync";
    private static final String GOODCANG_STORAGE_TASK =
            "goodcang_wh_inventory_storage_sync";
    private static final String SERVICE_NAME = "Python绩效ETL";
    private static final String RUN_PREFIX = "/api/v1/internal/scheduler/runs/";
    /** 轮询连续失败（如 Python 正在重启）达到该次数才判定失败。 */
    private static final int MAX_CONSECUTIVE_POLL_FAILURES = 6;
    private static final Logger LOG =
            LoggerFactory.getLogger(PythonPerformanceSchedulerClient.class);

    private final PythonPerformanceTaskProperties taskProperties;

    public PythonPerformanceSchedulerClient(
            PythonPerformanceTaskProperties properties,
            ObjectMapper objectMapper)
    {
        super(properties, objectMapper);
        this.taskProperties = properties;
    }

    public Map<String, Object> runPreviousMonth(String requestId)
    {
        return run(PERFORMANCE_TASK, null, requestId);
    }

    public Map<String, Object> runWeeklyInventory(String requestId)
    {
        return run("weekly_inventory_bin_export", null, requestId);
    }

    public Map<String, Object> runEbayMixedSalesPrices(String requestId)
    {
        return run("ebay_mixed_sales_price_sync", null, requestId);
    }

    public Map<String, Object> runGoodcangStorage(String requestId)
    {
        return run(GOODCANG_STORAGE_TASK, null, requestId);
    }

    public Map<String, Object> runEbayStoreListing(String requestId)
    {
        return run("ebay_store_listing_sync", null, requestId);
    }

    /** eBay价格分析刷表：整表读当前在售刊登快照，重算 DWS 并事务替换。 */
    public Map<String, Object> runEbayPriceAnalysisRefresh(String requestId)
    {
        return run("ebay_price_analysis_refresh", null, requestId);
    }

    public Map<String, Object> runEbayTokenHealth(String requestId)
    {
        return run("ebay_token_health_check", null, requestId);
    }

    public Map<String, Object> runFeishuBadTransaction(String requestId)
    {
        return run("feishu_bad_transaction_sync", null, requestId);
    }

    /** 负责人映射表从飞书多维表格同步；内容未变时 Python 直接跳过。 */
    public Map<String, Object> runOwnerRuleFeishu(String requestId)
    {
        return run("owner_rule_feishu_sync", null, requestId);
    }

    /** Read sanitized local credential expiry metadata; never fetch tokens or listings. */
    public Map<String, Object> ebayCredentialExpiry(String requestId)
    {
        try
        {
            HttpResponse<String> response = httpClient.send(baseRequest(
                    "/api/v1/internal/scheduler/ebay-credentials/expiry", requestId).GET().build(),
                    HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
            Map<String, Object> json = parseJson(response.body());
            if (response.statusCode() != 200 || integer(json.get("code"), -1) != 0)
                throw new IllegalStateException("eBay凭证有效期检查失败，HTTP=" + response.statusCode());
            return json;
        }
        catch (InterruptedException e)
        {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("eBay凭证有效期检查被中断");
        }
        catch (Exception e)
        {
            throw new IllegalStateException("eBay凭证有效期检查失败；未输出敏感响应");
        }
    }

    public Map<String, Object> runAmzListingRaw(String requestId)
    {
        return run("lingxing_amz_listing_raw_sync", null, requestId);
    }

    public Map<String, Object> runAmzProfitReport(String statMonth, String requestId)
    {
        return run("amz_profit_report_sync", statMonth, requestId);
    }

    public Map<String, Object> run(String statMonth, String requestId)
    {
        return run(PERFORMANCE_TASK, statMonth, requestId);
    }

    public Map<String, Object> runClearance(
            String pullMonth, String requestId)
    {
        return run(CLEARANCE_TASK, pullMonth, requestId);
    }

    public Map<String, Object> runInventoryReportSources(
            String statMonth, String requestId)
    {
        return run(INVENTORY_REPORT_SOURCE_TASK, statMonth, requestId);
    }

    public Map<String, Object> runInventoryPurchaseOrders(String requestId)
    {
        return run("monthly_inventory_purchase_order_sync", null, requestId);
    }

    public Map<String, Object> runInventoryReportSalesVolume(
            String statMonth, String requestId)
    {
        return run(INVENTORY_REPORT_SALES_VOLUME_TASK, statMonth, requestId);
    }

    public Map<String, Object> runInventoryReportOpeningInventory(
            String statMonth, String requestId)
    {
        return run(
                INVENTORY_REPORT_OPENING_INVENTORY_TASK,
                statMonth,
                requestId);
    }

    public Map<String, Object> runInventoryReportSalesSnapshotRefresh(
            String statMonth, String requestId)
    {
        return run(
                INVENTORY_REPORT_SALES_SNAPSHOT_REFRESH_TASK,
                statMonth,
                requestId);
    }

    public Map<String, Object> runCurrencyMonth(
            String statMonth, String requestId)
    {
        return run(CURRENCY_MONTH_TASK, statMonth, requestId);
    }

    private Map<String, Object> run(
            String taskCode, String statMonth, String requestId)
    {
        String triggerType = "JOB";
        try
        {
            Map<String, Object> payload = new LinkedHashMap<>();
            if (CLEARANCE_TASK.equals(taskCode)
                    || INVENTORY_REPORT_SOURCE_TASK.equals(taskCode)
                    || INVENTORY_REPORT_SALES_VOLUME_TASK.equals(taskCode)
                    || INVENTORY_REPORT_OPENING_INVENTORY_TASK.equals(taskCode))
                payload.put("pull_month", statMonth);
            else
                payload.put("stat_month", statMonth);
            String body = objectMapper.writeValueAsString(payload);
            String effectiveRequestId = effectiveRequestId(requestId);
            // 先异步提交拿到 run_id 再轮询，不再用一条 HTTP 连接等待数小时的 ETL。
            HttpResponse<String> accepted = httpClient.send(
                    taskRequest(taskCode + "/runs", body, triggerType,
                            effectiveRequestId, taskProperties.getPollRequestTimeout()),
                    HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
            if (accepted.statusCode() == 404 || accepted.statusCode() == 405)
            {
                // 兼容尚未部署异步接口的旧版 Python：退回同步调用。
                LOG.warn("Python未提供异步任务接口，按同步方式执行 task={}", taskCode);
                return runSynchronously(taskCode, body, triggerType, effectiveRequestId);
            }
            Map<String, Object> acceptedJson = parseJson(accepted.body());
            if (accepted.statusCode() != 202 || integer(acceptedJson.get("code"), -1) != 0)
                throw new IllegalStateException(errorMessage(accepted.statusCode(), acceptedJson));
            Object data = acceptedJson.get("data");
            Object runId = data instanceof Map<?, ?> map ? map.get("run_id") : null;
            if (runId == null || !StringUtils.hasText(String.valueOf(runId)))
                throw new IllegalStateException(SERVICE_NAME + "未返回运行ID");
            return poll(String.valueOf(runId), taskCode, effectiveRequestId);
        }
        catch (InterruptedException e)
        {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Python绩效ETL调用被中断", e);
        }
        catch (Exception e)
        {
            if (e instanceof IllegalStateException)
                throw (IllegalStateException) e;
            throw new IllegalStateException(
                    "调用Python绩效ETL失败: " + e.getMessage(), e);
        }
    }

    private HttpRequest taskRequest(String path, String body, String triggerType,
            String requestId, Duration timeout)
    {
        return baseRequest(TASK_PREFIX + path, requestId)
                .timeout(timeout)
                .header("Content-Type", "application/json;charset=utf-8")
                .header("X-Trigger-Type",
                        StringUtils.hasText(triggerType) ? triggerType : "JOB")
                .POST(HttpRequest.BodyPublishers.ofString(body, StandardCharsets.UTF_8))
                .build();
    }

    private Map<String, Object> runSynchronously(String taskCode, String body,
            String triggerType, String requestId) throws Exception
    {
        HttpResponse<String> response = httpClient.send(
                taskRequest(taskCode + "/run", body, triggerType, requestId,
                        Duration.ofMillis(taskProperties.getReadTimeoutMillis())),
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
        Map<String, Object> json = parseJson(response.body());
        validate(response.statusCode(), json, taskCode);
        return json;
    }

    private Map<String, Object> poll(String runId, String taskCode, String requestId)
            throws Exception
    {
        long deadline = System.nanoTime()
                + Duration.ofMillis(taskProperties.getReadTimeoutMillis()).toNanos();
        long intervalMillis = Math.max(1, taskProperties.getPollInterval().toMillis());
        int consecutiveFailures = 0;
        while (System.nanoTime() < deadline)
        {
            Thread.sleep(intervalMillis);
            HttpRequest request = baseRequest(RUN_PREFIX + url(runId), requestId)
                    .timeout(taskProperties.getPollRequestTimeout())
                    .GET()
                    .build();
            HttpResponse<String> response;
            try
            {
                response = httpClient.send(request,
                        HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
            }
            catch (IOException e)
            {
                if (++consecutiveFailures >= MAX_CONSECUTIVE_POLL_FAILURES)
                    throw new IllegalStateException(
                            SERVICE_NAME + "运行状态查询连续失败: " + e.getMessage(), e);
                LOG.warn("查询Python任务状态失败，稍后重试 task={} run={}: {}",
                        taskCode, runId, e.getMessage());
                continue;
            }
            consecutiveFailures = 0;
            if (response.statusCode() == 202)
                continue;
            Map<String, Object> json = parseJson(response.body());
            validate(response.statusCode(), json, taskCode);
            return json;
        }
        throw new IllegalStateException(SERVICE_NAME + "执行超时 task=" + taskCode
                + " run=" + runId + "，任务可能仍在Python中运行，请到任务运行记录中确认");
    }

    @SuppressWarnings("unchecked")
    private void validate(
            int status, Map<String, Object> json, String taskCode)
    {
        // 同步接口完成时返回 201，异步轮询完成时返回 200，结果体相同。
        if (status != 201 && status != 200)
            throw new IllegalStateException(errorMessage(status, json));
        if (integer(json.get("code"), -1) != 0)
            throw new IllegalStateException(errorMessage(status, json));
        Object dataValue = json.get("data");
        Map<String, Object> data = dataValue instanceof Map<?, ?>
                ? (Map<String, Object>) dataValue : Map.of();
        if (!"completed".equals(String.valueOf(data.get("status"))))
            throw new IllegalStateException(
                    "Python任务未完成: status=" + data.get("status"));
        Object resultValue = data.get("result");
        Map<String, Object> result = resultValue instanceof Map<?, ?>
                ? (Map<String, Object>) resultValue : Map.of();
        if (GOODCANG_STORAGE_TASK.equals(taskCode))
        {
            int summaries = integer(result.get("summary_rows"), -1);
            int details = integer(result.get("detail_rows"), -1);
            int bills = integer(result.get("bill_count"), -1);
            if (summaries < 0 || details < 0 || bills < 0
                    || integer(result.get("completed_bills"), -1) != bills
                    || integer(result.get("summary_ods_rows"), -1) != summaries
                    || integer(result.get("detail_ods_rows"), -1) != details
                    || integer(result.get("ods_rows"), -1) != summaries + details)
                throw new IllegalStateException(
                        "Python未返回完整的仓租概要及明细同步结果，请确认已部署并重启最新Python服务");
        }
        if (PERFORMANCE_TASK.equals(taskCode))
        {
            Object refreshValue = result.get("refresh");
            Map<String, Object> refresh = refreshValue instanceof Map<?, ?>
                    ? (Map<String, Object>) refreshValue : Map.of();
            if (!"completed".equals(String.valueOf(refresh.get("status"))))
                throw new IllegalStateException(
                        "Python ETL成功但排名刷新未完成: status="
                        + refresh.get("status"));
        }
    }

    private String errorMessage(int status, Map<String, Object> json)
    {
        Object detail = json.get("detail");
        if (detail != null)
            return SERVICE_NAME + "错误[HTTP " + status + "]: " + detail;
        Object message = json.get("message");
        if (message != null)
            return SERVICE_NAME + "错误[HTTP " + status + "]: " + message;
        return SERVICE_NAME + "请求失败，HTTP " + status;
    }
}
