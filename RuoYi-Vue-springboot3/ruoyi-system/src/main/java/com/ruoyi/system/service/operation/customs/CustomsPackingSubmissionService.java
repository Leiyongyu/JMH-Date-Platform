package com.ruoyi.system.service.operation.customs;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.system.domain.operation.customs.CustomsPackingSavedPayload;
import com.ruoyi.system.domain.operation.customs.CustomsPackingSubmission;
import com.ruoyi.system.mapper.operation.customs.CustomsPackingSubmissionMapper;
import com.ruoyi.system.service.operation.external.lingxing.LingxingGatewayService;
import com.ruoyi.system.service.operation.sync.SyncAlertService;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.Executor;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.util.StringUtils;

/** 将历史保存成功的STA装箱快照聚合、提交并跟踪领星异步结果。 */
@Service
public class CustomsPackingSubmissionService
{
    private static final Logger LOG =
            LoggerFactory.getLogger(CustomsPackingSubmissionService.class);
    private static final String SUBMIT_API =
            "amzStaServer/openapi/inbound-packing/setPackingInformation";
    private static final String STATUS_API =
            "amzStaServer/openapi/task-plan/operate";
    private static final long REQUEST_INTERVAL_MS = 1100L;
    private static final long ACTIVE_POLL_INTERVAL_MS = 3000L;
    private static final int ACTIVE_POLL_ATTEMPTS = 20;

    private final CustomsPackingSubmissionMapper mapper;
    private final LingxingGatewayService gateway;
    private final ObjectMapper objectMapper;
    private final Executor taskExecutor;
    private final SyncAlertService alertService;
    private final TransactionTemplate transactionTemplate;
    private final Object requestLock = new Object();
    private long lastRequestAt;

    public CustomsPackingSubmissionService(
            CustomsPackingSubmissionMapper mapper,
            LingxingGatewayService gateway,
            ObjectMapper objectMapper,
            @Qualifier("customsImportTaskExecutor") Executor taskExecutor,
            SyncAlertService alertService,
            TransactionTemplate transactionTemplate)
    {
        this.mapper = mapper;
        this.gateway = gateway;
        this.objectMapper = objectMapper;
        this.taskExecutor = taskExecutor;
        this.alertService = alertService;
        this.transactionTemplate = transactionTemplate;
    }

    public List<CustomsPackingSubmission> list(
            String inboundPlanId, String status)
    {
        return mapper.selectCandidateList(trim(inboundPlanId), upper(status));
    }

    public CustomsPackingSubmission get(Long id)
    {
        CustomsPackingSubmission submission = mapper.selectById(id);
        if (submission == null)
            throw new IllegalArgumentException("装箱提交记录不存在");
        return submission;
    }

    public CustomsPackingSubmission submit(
            String inboundPlanId, String operator)
    {
        String planId = trim(inboundPlanId);
        if (!StringUtils.hasText(planId))
            throw new IllegalArgumentException("STA任务编号不能为空");

        Long submissionId = transactionTemplate.execute(status ->
        {
            PreparedPayload prepared = preparePayload(planId);
            CustomsPackingSubmission initial = new CustomsPackingSubmission();
            initial.setInboundPlanId(planId);
            initial.setSid(prepared.sid);
            initial.setPositionType(prepared.positionType);
            mapper.insertReady(initial);

            int claimed = mapper.claimForSubmit(planId, defaultOperator(operator));
            if (claimed != 1)
            {
                CustomsPackingSubmission current =
                        mapper.selectByInboundPlanId(planId);
                String currentStatus = current == null ? "UNKNOWN" : current.getStatus();
                throw new IllegalStateException(statusMessage(currentStatus));
            }

            CustomsPackingSubmission claimedSubmission =
                    mapper.selectByInboundPlanId(planId);
            if (claimedSubmission == null || claimedSubmission.getId() == null)
                throw new IllegalStateException("装箱提交记录抢占成功但无法重新读取");
            int preparedRows = mapper.updatePrepared(
                    claimedSubmission.getId(),
                    prepared.sid,
                    prepared.positionType,
                    sha256(prepared.requestJson),
                    prepared.requestJson);
            if (preparedRows != 1)
                throw new IllegalStateException("装箱提交请求保存失败");
            return claimedSubmission.getId();
        });
        if (submissionId == null)
            throw new IllegalStateException("装箱提交事务未返回记录ID");

        try
        {
            taskExecutor.execute(() -> executeSubmission(submissionId));
        }
        catch (RuntimeException e)
        {
            String message = "后台任务提交失败，领星接口尚未调用：" + safeMessage(e);
            mapper.updateAfterSubmit(
                    submissionId, "FAILED", null, null, null, message);
            throw new IllegalStateException(message, e);
        }
        return mapper.selectById(submissionId);
    }

    public CustomsPackingSubmission refreshStatus(Long id)
    {
        CustomsPackingSubmission submission = get(id);
        if ("SUCCESS".equals(submission.getStatus()))
            return submission;
        if (!StringUtils.hasText(submission.getTaskId()))
            throw new IllegalStateException(
                    "该记录没有领星taskId，无法查询异步状态，请查看提交错误信息");
        if (!Set.of("PROCESSING", "UNKNOWN").contains(submission.getStatus()))
            throw new IllegalStateException("当前状态不需要查询领星异步结果");
        queryAndUpdateStatus(submission);
        return mapper.selectById(id);
    }

    private PreparedPayload preparePayload(String inboundPlanId)
    {
        List<CustomsPackingSavedPayload> saved =
                mapper.selectLatestSavedPayloads(inboundPlanId);
        if (saved.isEmpty())
            throw new IllegalArgumentException(
                    "未找到该STA保存成功的装箱信息");

        Integer positionType =
                mapper.selectPositionTypeByInboundPlanId(inboundPlanId);
        if (positionType == null)
            throw new IllegalArgumentException("STA任务缺少分仓方式positionType");
        if (positionType != 2)
            throw new IllegalArgumentException(
                    "当前仅支持先分仓后装箱(positionType=2)的STA提交；"
                            + "该任务positionType=" + positionType);

        int expected = mapper.countExpectedShipments(inboundPlanId);
        if (expected <= 0)
            throw new IllegalArgumentException("STA任务没有本地货件明细");
        if (saved.size() != expected)
            throw new IllegalArgumentException(
                    "STA装箱保存不完整：已保存 " + saved.size()
                            + " 个货件，应有 " + expected + " 个货件");

        Long sid = null;
        Set<String> shipmentIds = new LinkedHashSet<>();
        List<Map<String, Object>> packageGroupings = new ArrayList<>();
        for (CustomsPackingSavedPayload payload : saved)
        {
            Map<String, Object> request = jsonMap(payload.getRequestBody());
            String requestPlanId = text(request.get("inboundPlanId"));
            String shipmentId = text(request.get("shipmentId"));
            Long requestSid = longValue(request.get("sid"));
            List<Object> boxes = listValue(request.get("boxes"));

            if (!inboundPlanId.equals(requestPlanId))
                throw new IllegalArgumentException(
                        "保存日志中的STA编号不一致，日志ID=" + payload.getLogId());
            if (!StringUtils.hasText(shipmentId))
                throw new IllegalArgumentException(
                        "保存日志缺少内部shipmentId，日志ID=" + payload.getLogId());
            if (!shipmentIds.add(shipmentId))
                throw new IllegalArgumentException(
                        "存在重复的内部shipmentId：" + shipmentId);
            if (requestSid == null)
                throw new IllegalArgumentException(
                        "保存日志缺少SID，日志ID=" + payload.getLogId());
            if (sid == null) sid = requestSid;
            else if (!sid.equals(requestSid))
                throw new IllegalArgumentException("同一STA的保存日志存在多个SID");
            if (boxes.isEmpty())
                throw new IllegalArgumentException(
                        "货件 " + shipmentId + " 的箱子信息为空");

            Map<String, Object> grouping = new LinkedHashMap<>();
            grouping.put("boxes", boxes);
            grouping.put("shipmentId", shipmentId);
            packageGroupings.add(grouping);
        }

        Map<String, Object> request = new LinkedHashMap<>();
        request.put("inboundPlanId", inboundPlanId);
        request.put("packageGroupings", packageGroupings);
        request.put("sid", sid);
        return new PreparedPayload(
                sid, positionType, toJson(request));
    }

    private void executeSubmission(Long id)
    {
        CustomsPackingSubmission submission = mapper.selectById(id);
        if (submission == null || !"SUBMITTING".equals(submission.getStatus()))
            return;
        try
        {
            Map<String, Object> request = jsonMap(submission.getRequestBody());
            Map<String, Object> response = postRateLimited(SUBMIT_API, request);
            String responseJson = toJson(response);
            if (!codeSuccess(response))
            {
                mapper.updateAfterSubmit(id, "FAILED", null,
                        responseRequestId(response), responseJson,
                        responseMessage(response));
                return;
            }

            Map<String, Object> data = mapValue(response.get("data"));
            String taskId = text(data.get("taskId"));
            String taskStatus = lower(data.get("taskStatus"));
            String error = firstText(
                    text(data.get("errorMsg")), responseMessage(response));

            if ("success".equals(taskStatus))
            {
                mapper.updateAfterSubmit(id, "SUCCESS", taskId,
                        responseRequestId(response), responseJson, null);
                return;
            }
            if (isFailure(taskStatus))
            {
                mapper.updateAfterSubmit(id, "FAILED", taskId,
                        responseRequestId(response), responseJson, error);
                return;
            }
            if (!StringUtils.hasText(taskId))
            {
                mapper.updateAfterSubmit(id, "UNKNOWN", null,
                        responseRequestId(response), responseJson,
                        "领星已返回成功码但未返回taskId，无法确认最终结果");
                return;
            }

            mapper.updateAfterSubmit(id, "PROCESSING", taskId,
                    responseRequestId(response), responseJson, null);
            pollActively(id);
        }
        catch (Exception e)
        {
            LOG.error("STA装箱提交调用异常，submissionId={}", id, e);
            mapper.updateAfterSubmit(id, "UNKNOWN", null, null, null,
                    "提交接口调用异常，无法确认领星是否受理：" + safeMessage(e));
        }
    }

    private void pollActively(Long id)
    {
        for (int attempt = 0; attempt < ACTIVE_POLL_ATTEMPTS; attempt++)
        {
            sleep(ACTIVE_POLL_INTERVAL_MS);
            CustomsPackingSubmission current = mapper.selectById(id);
            if (current == null
                    || !Set.of("PROCESSING", "UNKNOWN").contains(current.getStatus())
                    || !StringUtils.hasText(current.getTaskId()))
                return;
            queryAndUpdateStatus(current);
            CustomsPackingSubmission updated = mapper.selectById(id);
            if (updated == null
                    || !Set.of("PROCESSING", "UNKNOWN").contains(updated.getStatus()))
                return;
        }
    }

    private void queryAndUpdateStatus(CustomsPackingSubmission submission)
    {
        try
        {
            Map<String, Object> request =
                    Map.of("taskId", submission.getTaskId());
            Map<String, Object> response = postRateLimited(STATUS_API, request);
            String responseJson = toJson(response);
            if (!codeSuccess(response))
            {
                mapper.updateAfterPoll(submission.getId(), submission.getStatus(),
                        responseRequestId(response), responseJson,
                        responseMessage(response));
                return;
            }

            Map<String, Object> data = mapValue(response.get("data"));
            String returnedTaskId = text(data.get("taskId"));
            if (StringUtils.hasText(returnedTaskId)
                    && !submission.getTaskId().equals(returnedTaskId))
            {
                mapper.updateAfterPoll(submission.getId(), "UNKNOWN",
                        responseRequestId(response), responseJson,
                        "领星返回taskId与本地记录不一致");
                return;
            }
            String returnedPlanId = text(data.get("inboundPlanId"));
            if (StringUtils.hasText(returnedPlanId)
                    && !submission.getInboundPlanId().equals(returnedPlanId))
            {
                mapper.updateAfterPoll(submission.getId(), "UNKNOWN",
                        responseRequestId(response), responseJson,
                        "领星返回inboundPlanId与本地记录不一致");
                return;
            }

            String taskStatus = lower(data.get("taskStatus"));
            String nextStatus = "process".equals(taskStatus)
                    ? "PROCESSING"
                    : "success".equals(taskStatus)
                    ? "SUCCESS"
                    : isFailure(taskStatus)
                    ? "FAILED" : "UNKNOWN";
            String error = "FAILED".equals(nextStatus)
                    ? firstText(text(data.get("errorMsg")), responseMessage(response))
                    : "UNKNOWN".equals(nextStatus)
                    ? "领星返回未知任务状态：" + taskStatus
                    : null;
            mapper.updateAfterPoll(submission.getId(), nextStatus,
                    responseRequestId(response), responseJson, error);
        }
        catch (Exception e)
        {
            LOG.warn("查询STA装箱异步状态失败，submissionId={}, taskId={}: {}",
                    submission.getId(), submission.getTaskId(), safeMessage(e));
            mapper.updateAfterPoll(submission.getId(), submission.getStatus(),
                    null, submission.getFinalResponseBody(),
                    "查询领星异步状态失败，稍后将自动重试：" + safeMessage(e));
        }
    }

    /** 服务重启或主动轮询结束后，继续补偿查询未完成任务。 */
    @Scheduled(fixedDelay = 60000L)
    public void recoverPendingSubmissions()
    {
        try
        {
            for (CustomsPackingSubmission submission : mapper.selectPending(20))
                queryAndUpdateStatus(submission);
            alertService.notifyBackgroundRecovery(
                    "sta_packing_recovery", "STA装箱提交补偿轮询");
        }
        catch (Exception e)
        {
            LOG.warn("STA装箱提交补偿查询失败：{}", safeMessage(e), e);
            alertService.notifyBackgroundFailure(
                    "sta_packing_recovery", "STA装箱提交补偿轮询", safeMessage(e));
        }
    }

    private Map<String, Object> postRateLimited(
            String api, Map<String, Object> request) throws Exception
    {
        synchronized (requestLock)
        {
            long wait = REQUEST_INTERVAL_MS
                    - (System.currentTimeMillis() - lastRequestAt);
            if (wait > 0) sleep(wait);
            try { return gateway.post(api, request); }
            finally { lastRequestAt = System.currentTimeMillis(); }
        }
    }

    private boolean codeSuccess(Map<String, Object> response)
    {
        if (response == null) return false;
        Object code = response.get("code");
        return (code instanceof Number && ((Number) code).intValue() == 0)
                || "0".equals(text(code));
    }

    private boolean isFailure(String status)
    {
        return "failure".equals(status) || "local_failure".equals(status);
    }

    private String responseRequestId(Map<String, Object> response)
    {
        return response == null ? null : firstText(
                text(response.get("requestId")), text(response.get("request_id")));
    }

    private String responseMessage(Map<String, Object> response)
    {
        if (response == null) return "领星接口返回空响应";
        String details = response.get("errorDetails") == null
                ? null : toJson(response.get("errorDetails"));
        return firstText(
                text(response.get("message")),
                text(response.get("error_details")),
                details,
                "领星接口返回失败");
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> mapValue(Object value)
    {
        if (value instanceof Map<?, ?>) return (Map<String, Object>) value;
        if (value == null) return new LinkedHashMap<>();
        return objectMapper.convertValue(
                value, new TypeReference<Map<String, Object>>() {});
    }

    private Map<String, Object> jsonMap(String json)
    {
        try
        {
            return objectMapper.readValue(
                    json, new TypeReference<Map<String, Object>>() {});
        }
        catch (Exception e)
        {
            throw new IllegalArgumentException("保存的装箱请求JSON无法解析", e);
        }
    }

    @SuppressWarnings("unchecked")
    private List<Object> listValue(Object value)
    {
        return value instanceof List<?> ? (List<Object>) value : new ArrayList<>();
    }

    private Long longValue(Object value)
    {
        if (value instanceof Number) return ((Number) value).longValue();
        String text = text(value);
        if (!StringUtils.hasText(text)) return null;
        try { return Long.parseLong(text); }
        catch (NumberFormatException e) { return null; }
    }

    private String toJson(Object value)
    {
        try { return objectMapper.writeValueAsString(value); }
        catch (Exception e) { throw new IllegalStateException("JSON序列化失败", e); }
    }

    private String sha256(String value)
    {
        try
        {
            return HexFormat.of().formatHex(
                    MessageDigest.getInstance("SHA-256")
                            .digest(value.getBytes(StandardCharsets.UTF_8)));
        }
        catch (Exception e)
        {
            throw new IllegalStateException("计算提交内容摘要失败", e);
        }
    }

    private String statusMessage(String status)
    {
        return switch (status)
        {
            case "SUBMITTING" -> "该STA正在提交，请勿重复操作";
            case "PROCESSING" -> "该STA已由领星受理，正在处理中";
            case "SUCCESS" -> "该STA已经提交成功，禁止重复提交";
            case "UNKNOWN" -> "该STA提交结果待确认，禁止直接重复提交";
            default -> "该STA当前状态不允许提交：" + status;
        };
    }

    private String text(Object value)
    {
        String result = value == null ? null : String.valueOf(value).trim();
        return StringUtils.hasText(result) ? result : null;
    }

    private String lower(Object value)
    {
        String result = text(value);
        return result == null ? "" : result.toLowerCase(Locale.ROOT);
    }

    private String upper(String value)
    {
        String result = trim(value);
        return result == null ? null : result.toUpperCase(Locale.ROOT);
    }

    private String trim(String value)
    {
        return value == null ? null : value.trim();
    }

    private String defaultOperator(String operator)
    {
        return StringUtils.hasText(trim(operator)) ? trim(operator) : "unknown";
    }

    private String firstText(String... values)
    {
        for (String value : values)
            if (StringUtils.hasText(value)) return value;
        return null;
    }

    private String safeMessage(Throwable throwable)
    {
        if (throwable == null) return "";
        return StringUtils.hasText(throwable.getMessage())
                ? throwable.getMessage() : throwable.getClass().getSimpleName();
    }

    private void sleep(long millis)
    {
        try { Thread.sleep(millis); }
        catch (InterruptedException e) { Thread.currentThread().interrupt(); }
    }

    private record PreparedPayload(
            Long sid, Integer positionType, String requestJson)
    {
    }
}
