package com.ruoyi.system.service.operation.customs;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.system.domain.operation.customs.CustomsShipmentFeeImportBatch;
import com.ruoyi.system.domain.operation.customs.CustomsShipmentFeeImportLog;
import com.ruoyi.system.domain.operation.external.LingxingStaPackingContext;
import com.ruoyi.system.mapper.operation.customs.CustomsShipmentFeeImportBatchMapper;
import com.ruoyi.system.mapper.operation.customs.CustomsShipmentFeeImportLogMapper;
import com.ruoyi.system.mapper.operation.external.LingxingStaInboundPlanMapper;
import com.ruoyi.system.service.operation.external.lingxing.LingxingGatewayService;
import com.ruoyi.system.service.operation.external.lingxing.LingxingStaInboundPlanSyncService;
import java.io.PrintWriter;
import java.io.StringWriter;
import java.math.BigDecimal;
import java.security.MessageDigest;
import java.time.Duration;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.Executor;
import org.apache.poi.ss.usermodel.Cell;
import org.apache.poi.ss.usermodel.DataFormatter;
import org.apache.poi.ss.usermodel.FormulaEvaluator;
import org.apache.poi.ss.usermodel.Row;
import org.apache.poi.ss.usermodel.Sheet;
import org.apache.poi.ss.usermodel.Workbook;
import org.apache.poi.ss.usermodel.WorkbookFactory;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;
import org.springframework.web.multipart.MultipartFile;

/**
 * 按“装箱信息模版.xlsx”逐个货件保存装箱信息到领星ERP，并复用发货单上传批次/明细日志。
 *
 * <p>一个请求对应一个FBA货件号；同组的每个Excel数据行表示一个箱子。
 * STA编号、SID、领星内部货件ID和MSKU均从STA拆分表自动补齐。
 * 该接口只保存到领星ERP，不提交亚马逊。</p>
 */
@Service
public class CustomsPackingInfoImportService
{
    private static final Logger LOG =
            LoggerFactory.getLogger(CustomsPackingInfoImportService.class);
    public static final String BUSINESS_TYPE = "PACKING_INFO";
    private static final String API =
            "amzStaServer/openapi/inbound-packing/setLocalPackingInformation";
    private static final int COLUMN_COUNT = 11;
    private static final int MAX_ROWS = 5000;
    private static final long MAX_FILE_SIZE = 20L * 1024 * 1024;
    private static final int MAX_ATTEMPTS = 2;
    private static final long REQUEST_INTERVAL_MS = 1100L;
    private static final DateTimeFormatter BATCH_TIME =
            DateTimeFormatter.ofPattern("yyyyMMddHHmmssSSS");

    private static final List<String> EXPECTED_HEADERS = List.of(
            "货件号", "长", "宽", "高", "长度单位", "标签类型", "sku",
            "预处理提供方", "申报量", "重量单位", "重量单位值");

    private static final String[] SOURCE_KEYS = {
            "shipmentNo", "length", "width", "height", "unitOfMeasurement",
            "labelOwner", "sku", "prepOwner", "quantity", "weightUnit", "weightValue"
    };

    private final CustomsShipmentFeeImportBatchMapper batchMapper;
    private final CustomsShipmentFeeImportLogMapper logMapper;
    private final LingxingStaInboundPlanMapper staInboundPlanMapper;
    private final LingxingStaInboundPlanSyncService staInboundPlanSyncService;
    private final LingxingGatewayService gatewayService;
    private final ObjectMapper objectMapper;
    private final Executor taskExecutor;
    private final Object lingxingRequestLock = new Object();
    private long lastLingxingRequestAt;

    public CustomsPackingInfoImportService(
            CustomsShipmentFeeImportBatchMapper batchMapper,
            CustomsShipmentFeeImportLogMapper logMapper,
            LingxingStaInboundPlanMapper staInboundPlanMapper,
            LingxingStaInboundPlanSyncService staInboundPlanSyncService,
            LingxingGatewayService gatewayService,
            ObjectMapper objectMapper,
            @Qualifier("syncTaskExecutor") Executor taskExecutor)
    {
        this.batchMapper = batchMapper;
        this.logMapper = logMapper;
        this.staInboundPlanMapper = staInboundPlanMapper;
        this.staInboundPlanSyncService = staInboundPlanSyncService;
        this.gatewayService = gatewayService;
        this.objectMapper = objectMapper;
        this.taskExecutor = taskExecutor;
    }

    public Map<String, Object> importFile(MultipartFile file, String operator)
    {
        checkFile(file);
        byte[] fileBytes;
        try
        {
            fileBytes = file.getBytes();
        }
        catch (Exception e)
        {
            throw new IllegalArgumentException("读取上传文件失败：" + safeMessage(e), e);
        }

        LocalDateTime startedAt = LocalDateTime.now();
        CustomsShipmentFeeImportBatch batch = new CustomsShipmentFeeImportBatch();
        batch.setBusinessType(BUSINESS_TYPE);
        batch.setBatchNo(createBatchNo());
        batch.setOriginalFileName(file.getOriginalFilename());
        batch.setFileSize(file.getSize());
        batch.setFileSha256(sha256(fileBytes));
        batch.setTotalRows(0);
        batch.setTotalShipments(0);
        batch.setSuccessCount(0);
        batch.setFailedCount(0);
        batch.setStatus("QUEUED");
        batch.setOperator(defaultOperator(operator));
        batch.setUploadTime(startedAt);
        batch.setStartTime(startedAt);
        batchMapper.insert(batch);

        List<ExcelRow> rows;
        try
        {
            rows = parseWorkbook(fileBytes);
        }
        catch (Exception e)
        {
            finishBatchWithFatalError(batch, startedAt, "EXCEL_PARSE", e);
            throw new IllegalArgumentException(
                    "装箱信息Excel解析失败，批次号 " + batch.getBatchNo() + "：" + safeMessage(e), e);
        }

        Map<String, List<ExcelRow>> grouped = groupRows(rows);
        batch.setTotalRows(rows.size());
        batch.setTotalShipments(grouped.size());
        batchMapper.updateResult(batch);

        taskExecutor.execute(() -> processBatch(batch, grouped, startedAt));

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("businessType", BUSINESS_TYPE);
        result.put("batchId", batch.getId());
        result.put("batchNo", batch.getBatchNo());
        result.put("fileName", batch.getOriginalFileName());
        result.put("fileSha256", batch.getFileSha256());
        result.put("readRows", rows.size());
        result.put("totalShipments", grouped.size());
        result.put("successCount", 0);
        result.put("failedCount", 0);
        result.put("status", "QUEUED");
        result.put("durationMs", null);
        result.put("message", "文件校验通过，已进入后台队列");
        return result;
    }

    private void processBatch(
            CustomsShipmentFeeImportBatch batch,
            Map<String, List<ExcelRow>> grouped,
            LocalDateTime startedAt)
    {
        batch.setStatus("RUNNING");
        batch.setErrorMessage(null);
        batchMapper.updateResult(batch);
        int successCount = 0;
        int failedCount = 0;
        try
        {
            for (List<ExcelRow> taskRows : grouped.values())
            {
                ProcessResult result = processTask(batch, taskRows);
                if (result.success) successCount++;
                else failedCount++;
                batch.setSuccessCount(successCount);
                batch.setFailedCount(failedCount);
                batch.setErrorMessage("后台处理中：已完成 "
                        + (successCount + failedCount) + "/" + grouped.size());
                batchMapper.updateResult(batch);
            }

            LocalDateTime finishedAt = LocalDateTime.now();
            batch.setSuccessCount(successCount);
            batch.setFailedCount(failedCount);
            batch.setStatus(failedCount == 0 ? "SUCCESS"
                    : successCount == 0 ? "FAILED" : "PARTIAL_SUCCESS");
            batch.setFinishTime(finishedAt);
            batch.setDurationMs(Duration.between(startedAt, finishedAt).toMillis());
            batch.setErrorMessage(failedCount == 0 ? null
                    : "共 " + failedCount + " 个货件装箱保存失败，请查看上传日志");
            batchMapper.updateResult(batch);
        }
        catch (Exception e)
        {
            LOG.error("装箱信息后台批次处理失败，batchNo={}", batch.getBatchNo(), e);
            finishBatchWithFatalError(batch, startedAt, "ASYNC_PROCESS", e);
        }
    }

    private ProcessResult processTask(
            CustomsShipmentFeeImportBatch batch, List<ExcelRow> rows)
    {
        LocalDateTime startedAt = LocalDateTime.now();
        String shipmentNo = trim(rows.get(0).value(0));
        String businessKey = shipmentNo;

        CustomsShipmentFeeImportLog log = new CustomsShipmentFeeImportLog();
        log.setBatchId(batch.getId());
        log.setBusinessType(BUSINESS_TYPE);
        log.setOrderSn(businessKey);
        log.setSourceRows(rowNumbers(rows));
        log.setSourceRowCount(rows.size());
        log.setStatus("PROCESSING");
        log.setAttemptCount(0);
        log.setSourceData(toJson(sourceData(rows)));
        log.setOperator(batch.getOperator());
        log.setUploadTime(batch.getUploadTime());
        log.setStartTime(startedAt);
        logMapper.insert(log);

        List<String> validationErrors = validateRows(rows);
        Map<String, Object> request = null;
        if (validationErrors.isEmpty())
        {
            try
            {
                LingxingStaPackingContext context =
                        resolvePackingContext(shipmentNo, validationErrors);
                if (context != null)
                {
                    Map<Integer, String> resolvedMskuByRow =
                            resolveMskus(context.getRecordKey(), rows, validationErrors);
                    if (validationErrors.isEmpty())
                        request = buildRequest(rows, context, resolvedMskuByRow);
                }
            }
            catch (Exception e)
            {
                validationErrors.add("组装装箱请求失败：" + safeMessage(e));
            }
        }
        if (!validationErrors.isEmpty())
        {
            String message = String.join("；", validationErrors);
            finishFailed(log, startedAt, "VALIDATION", "PACKING_VALIDATION",
                    message, null, null, request, 0);
            return ProcessResult.failed(
                    businessKey, "VALIDATION", "PACKING_VALIDATION", message);
        }

        Map<String, Object> response = null;
        Exception lastException = null;
        int attempts = 0;
        for (int attempt = 1; attempt <= MAX_ATTEMPTS; attempt++)
        {
            attempts = attempt;
            try
            {
                response = postToLingxing(request);
                if (isSuccess(response) || !isRetryable(response) || attempt == MAX_ATTEMPTS)
                    break;
            }
            catch (Exception e)
            {
                lastException = e;
                if (attempt == MAX_ATTEMPTS) break;
            }
            sleepQuietly(1000L * attempt);
        }

        if (lastException != null && response == null)
        {
            String message = safeMessage(lastException);
            finishFailed(log, startedAt, "API_EXCEPTION", lastException.getClass().getSimpleName(),
                    message, lastException, null, request, attempts);
            return ProcessResult.failed(businessKey, "API_EXCEPTION",
                    lastException.getClass().getSimpleName(), message);
        }

        if (isSuccess(response))
        {
            LocalDateTime successAt = LocalDateTime.now();
            log.setStatus("SUCCESS");
            log.setErrorCode(valueText(response.get("code")));
            log.setErrorMessage(responseMessage(response));
            log.setRequestId(responseValue(response, "request_id", "requestId"));
            log.setLingxingResponseTime(responseValue(
                    response, "response_time", "responseTime"));
            log.setAttemptCount(attempts);
            log.setRequestBody(toJson(request));
            log.setResponseBody(toJson(response));
            log.setSuccessTime(successAt);
            log.setDurationMs(Duration.between(startedAt, successAt).toMillis());
            logMapper.updateResult(log);
            return ProcessResult.success(businessKey);
        }

        String code = response == null ? "EMPTY_RESPONSE" : valueText(response.get("code"));
        String message = response == null ? "领星接口返回空响应" : responseMessage(response);
        finishFailed(log, startedAt, "LINGXING_API", code, message,
                null, response, request, attempts);
        return ProcessResult.failed(businessKey, "LINGXING_API", code, message);
    }

    private List<ExcelRow> parseWorkbook(byte[] fileBytes) throws Exception
    {
        try (Workbook workbook = WorkbookFactory.create(
                new java.io.ByteArrayInputStream(fileBytes)))
        {
            Sheet sheet = workbook.getSheet("Sheet1");
            if (sheet == null)
                throw new IllegalArgumentException("模板中缺少 Sheet1 工作表");
            DataFormatter formatter = new DataFormatter(Locale.CHINA);
            FormulaEvaluator evaluator = workbook.getCreationHelper().createFormulaEvaluator();
            validateHeader(sheet, formatter, evaluator);

            List<ExcelRow> rows = new ArrayList<>();
            for (int rowIndex = 1; rowIndex <= sheet.getLastRowNum(); rowIndex++)
            {
                Row source = sheet.getRow(rowIndex);
                if (source == null) continue;
                String[] values = new String[COLUMN_COUNT];
                boolean hasValue = false;
                for (int col = 0; col < COLUMN_COUNT; col++)
                {
                    values[col] = cellText(source.getCell(col), formatter, evaluator);
                    if (StringUtils.hasText(values[col])) hasValue = true;
                }
                if (!hasValue) continue;
                rows.add(new ExcelRow(rowIndex + 1, values));
                if (rows.size() > MAX_ROWS)
                    throw new IllegalArgumentException("单次最多允许 " + MAX_ROWS + " 行装箱数据");
            }
            if (rows.isEmpty()) throw new IllegalArgumentException("Sheet1 中没有装箱数据");
            return rows;
        }
    }

    private void validateHeader(
            Sheet sheet, DataFormatter formatter, FormulaEvaluator evaluator)
    {
        Row header = sheet.getRow(0);
        if (header == null) throw new IllegalArgumentException("Sheet1 第一行表头为空");
        List<String> errors = new ArrayList<>();
        for (int col = 0; col < EXPECTED_HEADERS.size(); col++)
        {
            String actual = cellText(header.getCell(col), formatter, evaluator);
            if (!EXPECTED_HEADERS.get(col).equals(actual))
                errors.add(columnName(col) + "列应为“" + EXPECTED_HEADERS.get(col)
                        + "”，实际为“" + actual + "”");
        }
        for (int col = EXPECTED_HEADERS.size(); col < header.getLastCellNum(); col++)
        {
            String extra = cellText(header.getCell(col), formatter, evaluator);
            if (StringUtils.hasText(extra))
                errors.add(columnName(col) + "列为多余字段“" + extra + "”");
        }
        if (!errors.isEmpty())
            throw new IllegalArgumentException("装箱模板表头不匹配：" + String.join("；", errors));
    }

    private Map<String, List<ExcelRow>> groupRows(List<ExcelRow> rows)
    {
        Map<String, List<ExcelRow>> grouped = new LinkedHashMap<>();
        for (ExcelRow row : rows)
        {
            String shipmentNo = trim(row.value(0));
            String key = StringUtils.hasText(shipmentNo)
                    ? shipmentNo
                    : "__ROW_" + row.rowNo;
            grouped.computeIfAbsent(key, unused -> new ArrayList<>()).add(row);
        }
        return grouped;
    }

    private List<String> validateRows(List<ExcelRow> rows)
    {
        List<String> errors = new ArrayList<>();
        Set<String> shipmentNos = new LinkedHashSet<>();
        for (ExcelRow row : rows)
        {
            String prefix = "第" + row.rowNo + "行";
            required(row, 0, "货件号", prefix, errors);
            positiveDecimal(row, 1, "长", prefix, errors);
            positiveDecimal(row, 2, "宽", prefix, errors);
            positiveDecimal(row, 3, "高", prefix, errors);
            enumValue(row, 4, "长度单位", Set.of("IN", "CM"), prefix, errors);
            enumValue(row, 5, "标签类型",
                    Set.of("AMAZON", "SELLER", "NONE"), prefix, errors);
            required(row, 6, "sku", prefix, errors);
            enumValue(row, 7, "预处理提供方",
                    Set.of("AMAZON", "SELLER", "NONE"), prefix, errors);
            positiveInteger(row, 8, "申报量", prefix, errors);
            validateWeight(row, prefix, errors);
            if (StringUtils.hasText(trim(row.value(0))))
                shipmentNos.add(trim(row.value(0)));
        }
        if (shipmentNos.size() > 1)
            errors.add("同一保存任务中存在多个货件号：" + shipmentNos);
        return errors;
    }

    private void validateWeight(ExcelRow row, String prefix, List<String> errors)
    {
        String unit = upper(row.value(9));
        String value = trim(row.value(10));
        boolean hasUnit = StringUtils.hasText(unit);
        boolean hasValue = StringUtils.hasText(value);
        if (!hasUnit || !hasValue)
        {
            errors.add(prefix + "保存装箱信息时重量单位和重量单位值都必须填写");
            return;
        }
        if (!Set.of("LB", "KG").contains(unit))
            errors.add(prefix + "重量单位必须为LB或KG");
        positiveDecimal(row, 10, "重量单位值", prefix, errors);
    }

    private LingxingStaPackingContext resolvePackingContext(
            String shipmentNo, List<String> errors)
    {
        if (!StringUtils.hasText(shipmentNo)) return null;
        List<LingxingStaPackingContext> contexts =
                staInboundPlanMapper.selectPackingContextByShipmentNo(shipmentNo);
        try
        {
            // 每次上传都按货件号增量覆盖该STA任务，避免使用过期的SID、MSKU或内部货件ID。
            staInboundPlanSyncService.syncByShipmentId(shipmentNo);
            contexts = staInboundPlanMapper.selectPackingContextByShipmentNo(shipmentNo);
        }
        catch (Exception e)
        {
            if (contexts.isEmpty())
            {
                errors.add("货件号“" + shipmentNo + "”自动补拉STA任务失败："
                        + safeMessage(e));
                return null;
            }
            LOG.warn("货件号{}增量刷新STA失败，使用本地已同步关系：{}",
                    shipmentNo, safeMessage(e));
        }
        Map<String, LingxingStaPackingContext> distinct = new LinkedHashMap<>();
        for (LingxingStaPackingContext context : contexts)
        {
            String key = context.getInboundPlanId() + "\u0001" + context.getShipmentId();
            distinct.putIfAbsent(key, context);
        }
        if (distinct.isEmpty())
        {
            errors.add("货件号“" + shipmentNo + "”未在STA任务货件明细中找到");
            return null;
        }
        if (distinct.size() > 1)
        {
            errors.add("货件号“" + shipmentNo + "”匹配到多个STA任务或内部货件ID："
                    + distinct.keySet());
            return null;
        }
        LingxingStaPackingContext context = distinct.values().iterator().next();
        if (!StringUtils.hasText(context.getInboundPlanId()))
            errors.add("货件号“" + shipmentNo + "”缺少inboundPlanId");
        if (context.getSid() == null)
            errors.add("货件号“" + shipmentNo + "”对应STA任务缺少SID");
        if (!StringUtils.hasText(context.getShipmentId()))
            errors.add("货件号“" + shipmentNo + "”缺少领星内部shipmentId");
        if (!errors.isEmpty())
        {
            return null;
        }
        return context;
    }

    private Map<Integer, String> resolveMskus(
            String recordKey, List<ExcelRow> rows, List<String> errors)
    {
        Map<Integer, String> result = new LinkedHashMap<>();
        if (!StringUtils.hasText(recordKey)) return result;
        for (ExcelRow row : rows)
        {
            String skuOrMsku = trim(row.value(6));
            List<String> mskus =
                    staInboundPlanMapper.selectMskuBySkuOrMsku(recordKey, skuOrMsku);
            Set<String> distinct = new LinkedHashSet<>(mskus);
            if (distinct.isEmpty())
            {
                errors.add("第" + row.rowNo + "行商品MSKU“" + skuOrMsku
                        + "”未在STA任务商品明细中找到");
            }
            else if (distinct.size() > 1)
            {
                errors.add("第" + row.rowNo + "行商品“" + skuOrMsku
                        + "”匹配到多个MSKU：" + distinct);
            }
            else
            {
                result.put(row.rowNo, distinct.iterator().next());
            }
        }
        return result;
    }

    private Map<String, Object> buildRequest(
            List<ExcelRow> rows, LingxingStaPackingContext context,
            Map<Integer, String> resolvedMskuByRow)
    {
        Map<String, Object> request = new LinkedHashMap<>();
        List<Map<String, Object>> boxes = new ArrayList<>();
        for (ExcelRow row : rows)
            boxes.add(buildBox(row, resolvedMskuByRow.get(row.rowNo)));
        request.put("boxes", boxes);
        request.put("inboundPlanId", context.getInboundPlanId());
        request.put("shipmentId", context.getShipmentId());
        request.put("sid", context.getSid());
        return request;
    }

    private Map<String, Object> buildBox(ExcelRow row, String resolvedMsku)
    {
        Map<String, Object> dimensions = new LinkedHashMap<>();
        dimensions.put("height", decimalText(row.value(3)));
        dimensions.put("length", decimalText(row.value(1)));
        dimensions.put("unitOfMeasurement", upper(row.value(4)));
        dimensions.put("width", decimalText(row.value(2)));

        Map<String, Object> item = new LinkedHashMap<>();
        item.put("labelOwner", upper(row.value(5)));
        item.put("msku", resolvedMsku);
        item.put("prepOwner", upper(row.value(7)));
        item.put("quantity", integer(row.value(8)));

        Map<String, Object> box = new LinkedHashMap<>();
        box.put("dimensions", dimensions);
        box.put("items", List.of(item));
        Map<String, Object> weight = new LinkedHashMap<>();
        weight.put("unit", upper(row.value(9)));
        weight.put("value", decimalText(row.value(10)));
        box.put("weight", weight);
        return box;
    }

    private List<Map<String, Object>> sourceData(List<ExcelRow> rows)
    {
        List<Map<String, Object>> result = new ArrayList<>();
        for (ExcelRow row : rows)
        {
            Map<String, Object> data = new LinkedHashMap<>();
            data.put("excelRow", row.rowNo);
            for (int i = 0; i < SOURCE_KEYS.length; i++)
                data.put(SOURCE_KEYS[i], row.value(i));
            result.add(data);
        }
        return result;
    }

    private boolean isSuccess(Map<String, Object> response)
    {
        if (response == null) return false;
        Object code = response.get("code");
        boolean codeSuccess = (code instanceof Number && ((Number) code).intValue() == 0)
                || "0".equals(valueText(code));
        if (!codeSuccess) return false;
        Object data = response.get("data");
        if (!(data instanceof Map<?, ?> dataMap)) return true;
        String taskStatus = valueText(dataMap.get("taskStatus")).toLowerCase(Locale.ROOT);
        return !"failure".equals(taskStatus) && !"local_failure".equals(taskStatus);
    }

    private String responseMessage(Map<String, Object> response)
    {
        if (response == null) return "领星接口返回空响应";
        String message = firstText(
                valueText(response.get("message")),
                valueText(response.get("errorDetails")),
                valueText(response.get("error_details")));
        Object data = response.get("data");
        if (data instanceof Map<?, ?> dataMap)
            message = firstText(valueText(dataMap.get("errorMsg")), message);
        return StringUtils.hasText(message) ? message : "领星接口返回失败";
    }

    private boolean isRetryable(Map<String, Object> response)
    {
        if (response == null) return true;
        String code = valueText(response.get("code"));
        String message = responseMessage(response).toLowerCase(Locale.ROOT);
        return "429".equals(code) || message.contains("频繁") || message.contains("限流")
                || message.contains("timeout") || message.contains("超时");
    }

    private void finishFailed(
            CustomsShipmentFeeImportLog log, LocalDateTime startedAt,
            String stage, String code, String message, Exception exception,
            Map<String, Object> response, Map<String, Object> request, int attempts)
    {
        LocalDateTime failedAt = LocalDateTime.now();
        log.setStatus("FAILED");
        log.setErrorStage(stage);
        log.setErrorCode(code);
        log.setErrorMessage(message);
        log.setExceptionType(exception == null ? null : exception.getClass().getName());
        log.setStackTrace(exception == null ? null : stackTrace(exception));
        log.setRequestId(response == null ? null
                : responseValue(response, "request_id", "requestId"));
        log.setLingxingResponseTime(response == null ? null
                : responseValue(response, "response_time", "responseTime"));
        log.setAttemptCount(attempts);
        log.setRequestBody(request == null ? null : toJson(request));
        log.setResponseBody(response == null ? null : toJson(response));
        log.setFailedTime(failedAt);
        log.setDurationMs(Duration.between(startedAt, failedAt).toMillis());
        logMapper.updateResult(log);
    }

    private void finishBatchWithFatalError(
            CustomsShipmentFeeImportBatch batch, LocalDateTime startedAt,
            String stage, Exception exception)
    {
        LocalDateTime finishedAt = LocalDateTime.now();
        batch.setStatus("FAILED");
        batch.setFailedCount(0);
        batch.setErrorMessage(stage + "：" + safeMessage(exception));
        batch.setFinishTime(finishedAt);
        batch.setDurationMs(Duration.between(startedAt, finishedAt).toMillis());
        batchMapper.updateResult(batch);
    }

    private void required(
            ExcelRow row, int col, String label, String prefix, List<String> errors)
    {
        if (!StringUtils.hasText(trim(row.value(col))))
            errors.add(prefix + "缺少" + label);
    }

    private void enumValue(
            ExcelRow row, int col, String label, Set<String> allowed,
            String prefix, List<String> errors)
    {
        String value = upper(row.value(col));
        if (!StringUtils.hasText(value))
            errors.add(prefix + "缺少" + label);
        else if (!allowed.contains(value))
            errors.add(prefix + label + "必须为" + allowed + "之一，实际为：" + value);
    }

    private void positiveDecimal(
            ExcelRow row, int col, String label, String prefix, List<String> errors)
    {
        String value = trim(row.value(col));
        if (!StringUtils.hasText(value))
        {
            errors.add(prefix + "缺少" + label);
            return;
        }
        try
        {
            if (new BigDecimal(value.replace(",", "")).compareTo(BigDecimal.ZERO) <= 0)
                errors.add(prefix + label + "必须大于0");
        }
        catch (NumberFormatException e)
        {
            errors.add(prefix + label + "不是有效数字：" + value);
        }
    }

    private void positiveInteger(
            ExcelRow row, int col, String label, String prefix, List<String> errors)
    {
        String value = trim(row.value(col));
        if (!StringUtils.hasText(value))
        {
            errors.add(prefix + "缺少" + label);
            return;
        }
        try
        {
            if (new BigDecimal(value.replace(",", "")).intValueExact() <= 0)
                errors.add(prefix + label + "必须为正整数");
        }
        catch (Exception e)
        {
            errors.add(prefix + label + "不是有效正整数：" + value);
        }
    }

    private BigDecimal decimal(String value)
    {
        return new BigDecimal(trim(value).replace(",", ""));
    }

    private String decimalText(String value)
    {
        return decimal(value).stripTrailingZeros().toPlainString();
    }

    private Integer integer(String value)
    {
        return new BigDecimal(trim(value).replace(",", "")).intValueExact();
    }

    private String responseValue(
            Map<String, Object> response, String firstKey, String secondKey)
    {
        return firstText(valueText(response.get(firstKey)), valueText(response.get(secondKey)));
    }

    private void putIfNotBlank(Map<String, Object> target, String key, String value)
    {
        String normalized = trim(value);
        if (StringUtils.hasText(normalized)) target.put(key, normalized);
    }

    private String rowNumbers(List<ExcelRow> rows)
    {
        List<String> values = new ArrayList<>();
        for (ExcelRow row : rows) values.add(String.valueOf(row.rowNo));
        return String.join(",", values);
    }

    private String cellText(
            Cell cell, DataFormatter formatter, FormulaEvaluator evaluator)
    {
        if (cell == null) return "";
        String text = formatter.formatCellValue(cell, evaluator);
        return text == null ? "" : text.trim();
    }

    private void checkFile(MultipartFile file)
    {
        if (file == null || file.isEmpty())
            throw new IllegalArgumentException("请选择要上传的装箱信息Excel文件");
        if (file.getSize() > MAX_FILE_SIZE)
            throw new IllegalArgumentException("Excel文件不能超过20MB");
        String name = file.getOriginalFilename();
        String lower = name == null ? "" : name.toLowerCase(Locale.ROOT);
        if (!lower.endsWith(".xlsx") && !lower.endsWith(".xls"))
            throw new IllegalArgumentException("仅支持.xlsx或.xls文件");
    }

    private String sha256(byte[] bytes)
    {
        try
        {
            return HexFormat.of().formatHex(
                    MessageDigest.getInstance("SHA-256").digest(bytes));
        }
        catch (Exception e)
        {
            throw new IllegalStateException("计算文件摘要失败", e);
        }
    }

    private String createBatchNo()
    {
        return "CPI" + LocalDateTime.now().format(BATCH_TIME)
                + UUID.randomUUID().toString().replace("-", "")
                .substring(0, 6).toUpperCase(Locale.ROOT);
    }

    private String toJson(Object value)
    {
        if (value == null) return null;
        try { return objectMapper.writeValueAsString(value); }
        catch (Exception e) { return String.valueOf(value); }
    }

    private String stackTrace(Exception exception)
    {
        StringWriter writer = new StringWriter();
        exception.printStackTrace(new PrintWriter(writer));
        return writer.toString();
    }

    private String columnName(int index)
    {
        int value = index + 1;
        StringBuilder result = new StringBuilder();
        while (value > 0)
        {
            value--;
            result.insert(0, (char) ('A' + value % 26));
            value /= 26;
        }
        return result.toString();
    }

    private String defaultOperator(String operator)
    {
        return StringUtils.hasText(trim(operator)) ? trim(operator) : "unknown";
    }

    private String upper(String value)
    {
        String normalized = trim(value);
        return normalized == null ? null : normalized.toUpperCase(Locale.ROOT);
    }

    private String valueText(Object value)
    {
        return value == null ? "" : String.valueOf(value);
    }

    private String firstText(String... values)
    {
        return Arrays.stream(values).filter(StringUtils::hasText).findFirst().orElse("");
    }

    private String trim(String value)
    {
        return value == null ? null : value.trim();
    }

    private String safeMessage(Throwable throwable)
    {
        if (throwable == null) return "";
        String message = throwable.getMessage();
        return StringUtils.hasText(message) ? message : throwable.getClass().getSimpleName();
    }

    private Map<String, Object> postToLingxing(Map<String, Object> request)
            throws Exception
    {
        synchronized (lingxingRequestLock)
        {
            long elapsed = System.currentTimeMillis() - lastLingxingRequestAt;
            long waitMillis = REQUEST_INTERVAL_MS - elapsed;
            if (waitMillis > 0) sleepQuietly(waitMillis);
            try
            {
                return gatewayService.post(API, request);
            }
            finally
            {
                lastLingxingRequestAt = System.currentTimeMillis();
            }
        }
    }

    private void sleepQuietly(long millis)
    {
        try { Thread.sleep(millis); }
        catch (InterruptedException e) { Thread.currentThread().interrupt(); }
    }

    private static class ExcelRow
    {
        final int rowNo;
        final String[] values;

        ExcelRow(int rowNo, String[] values)
        {
            this.rowNo = rowNo;
            this.values = values;
        }

        String value(int index)
        {
            return index >= 0 && index < values.length ? values[index] : "";
        }
    }

    private static class ProcessResult
    {
        final boolean success;
        final String businessKey;
        final String errorStage;
        final String errorCode;
        final String errorMessage;

        private ProcessResult(
                boolean success, String businessKey, String errorStage,
                String errorCode, String errorMessage)
        {
            this.success = success;
            this.businessKey = businessKey;
            this.errorStage = errorStage;
            this.errorCode = errorCode;
            this.errorMessage = errorMessage;
        }

        static ProcessResult success(String businessKey)
        {
            return new ProcessResult(true, businessKey, null, null, null);
        }

        static ProcessResult failed(
                String businessKey, String errorStage,
                String errorCode, String errorMessage)
        {
            return new ProcessResult(
                    false, businessKey, errorStage, errorCode, errorMessage);
        }
    }
}
