package com.ruoyi.system.service.operation.customs;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.system.domain.operation.customs.CustomsShipmentFeeImportBatch;
import com.ruoyi.system.domain.operation.customs.CustomsShipmentFeeImportLog;
import com.ruoyi.system.mapper.operation.customs.CustomsShipmentFeeImportBatchMapper;
import com.ruoyi.system.mapper.operation.customs.CustomsShipmentFeeImportLogMapper;
import com.ruoyi.system.service.operation.external.lingxing.LingxingGatewayService;
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
import org.apache.poi.ss.usermodel.Cell;
import org.apache.poi.ss.usermodel.DataFormatter;
import org.apache.poi.ss.usermodel.FormulaEvaluator;
import org.apache.poi.ss.usermodel.Row;
import org.apache.poi.ss.usermodel.Sheet;
import org.apache.poi.ss.usermodel.Workbook;
import org.apache.poi.ss.usermodel.WorkbookFactory;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;
import org.springframework.web.multipart.MultipartFile;

/**
 * 按用户提供的“模版.xlsx”逐单更新领星发货单物流费用，并记录完整审计日志。
 */
@Service
public class CustomsShipmentFeeImportService
{
    public static final String BUSINESS_TYPE = "SHIPMENT_LOGISTICS";
    private static final String UPDATE_API =
            "erp/sc/routing/storage/shipment/updateListLogistics";
    private static final int COLUMN_COUNT = 28;
    private static final int MAX_ROWS = 2000;
    private static final long MAX_FILE_SIZE = 20L * 1024 * 1024;
    private static final int MAX_ATTEMPTS = 2;
    private static final long REQUEST_INTERVAL_MS = 350L;
    private static final DateTimeFormatter BATCH_TIME =
            DateTimeFormatter.ofPattern("yyyyMMddHHmmssSSS");

    private static final List<String> EXPECTED_HEADERS = List.of(
            "发货单号", "物流商id", "物流渠道商id", "运输类型", "单号类型",
            "费用明细-预估费用", "单价", "单价币种", "物流费用", "物流费用币种",
            "预估费用备注", "预估费用-其他费id", "其他费金额", "其他费币种",
            "费用明细-实际费用", "税费币种", "实重（单位：KG）", "体积（单位：m³）",
            "单价", "单价币种", "物流费用", "物流费用币种", "实际费用备注",
            "实际费用-其他费id", "其他费金额", "其他费币种", "物流商单号", "跟踪号");

    private static final String[] SOURCE_KEYS = {
            "order_sn", "logistics_provider_id", "logistics_channel_id",
            "transport_type", "order_type_code",
            "estimate_chargeable_weight", "estimate_price", "estimate_price_currency",
            "estimate_logistics_fee", "estimate_logistics_fee_currency", "estimate_remark",
            "estimate_other_fee_type_id", "estimate_other_amount", "estimate_other_currency",
            "actual_tax_fee", "actual_tax_fee_currency", "actual_weight", "actual_volume",
            "actual_price", "actual_price_currency", "actual_logistics_fee",
            "actual_logistics_fee_currency", "actual_remark",
            "actual_other_fee_type_id", "actual_other_amount", "actual_other_currency",
            "tracking_number", "replace_tracking_number"
    };

    private final CustomsShipmentFeeImportBatchMapper batchMapper;
    private final CustomsShipmentFeeImportLogMapper logMapper;
    private final LingxingGatewayService gatewayService;
    private final ObjectMapper objectMapper;

    public CustomsShipmentFeeImportService(
            CustomsShipmentFeeImportBatchMapper batchMapper,
            CustomsShipmentFeeImportLogMapper logMapper,
            LingxingGatewayService gatewayService,
            ObjectMapper objectMapper)
    {
        this.batchMapper = batchMapper;
        this.logMapper = logMapper;
        this.gatewayService = gatewayService;
        this.objectMapper = objectMapper;
    }

    public List<CustomsShipmentFeeImportBatch> listBatches(
            String businessType, String batchNo, String status, String operator)
    {
        return batchMapper.selectList(
                trim(businessType), trim(batchNo), trim(status), trim(operator));
    }

    public List<CustomsShipmentFeeImportLog> listLogs(
            String businessType, String batchNo, String orderSn, String status, String operator,
            String beginTime, String endTime)
    {
        return logMapper.selectList(
                trim(businessType), trim(batchNo), trim(orderSn), trim(status), trim(operator),
                trim(beginTime), normalizeEndTime(endTime));
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
        batch.setStatus("RUNNING");
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
                    "Excel解析失败，批次号 " + batch.getBatchNo() + "：" + safeMessage(e), e);
        }

        Map<String, List<ExcelRow>> grouped = groupRows(rows);
        batch.setTotalRows(rows.size());
        batch.setTotalShipments(grouped.size());

        int successCount = 0;
        int failedCount = 0;
        List<Map<String, Object>> failures = new ArrayList<>();

        for (Map.Entry<String, List<ExcelRow>> entry : grouped.entrySet())
        {
            List<ExcelRow> shipmentRows = entry.getValue();
            ProcessResult result = processShipment(batch, shipmentRows);
            if (result.success)
            {
                successCount++;
            }
            else
            {
                failedCount++;
                Map<String, Object> failure = new LinkedHashMap<>();
                failure.put("orderSn", result.orderSn);
                failure.put("sourceRows", rowNumbers(shipmentRows));
                failure.put("stage", result.errorStage);
                failure.put("code", result.errorCode);
                failure.put("message", result.errorMessage);
                failures.add(failure);
            }
            pauseBetweenRequests();
        }

        LocalDateTime finishedAt = LocalDateTime.now();
        batch.setSuccessCount(successCount);
        batch.setFailedCount(failedCount);
        batch.setStatus(failedCount == 0 ? "SUCCESS"
                : successCount == 0 ? "FAILED" : "PARTIAL_SUCCESS");
        batch.setFinishTime(finishedAt);
        batch.setDurationMs(Duration.between(startedAt, finishedAt).toMillis());
        batch.setErrorMessage(failedCount == 0 ? null
                : "共 " + failedCount + " 个发货单失败，请查看发货单日志");
        batchMapper.updateResult(batch);

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("batchId", batch.getId());
        result.put("batchNo", batch.getBatchNo());
        result.put("fileName", batch.getOriginalFileName());
        result.put("fileSha256", batch.getFileSha256());
        result.put("readRows", rows.size());
        result.put("totalShipments", grouped.size());
        result.put("successCount", successCount);
        result.put("failedCount", failedCount);
        result.put("status", batch.getStatus());
        result.put("durationMs", batch.getDurationMs());
        result.put("failures", failures);
        return result;
    }

    private ProcessResult processShipment(
            CustomsShipmentFeeImportBatch batch, List<ExcelRow> rows)
    {
        LocalDateTime startedAt = LocalDateTime.now();
        String orderSn = trim(rows.get(0).value(0));
        CustomsShipmentFeeImportLog log = new CustomsShipmentFeeImportLog();
        log.setBatchId(batch.getId());
        log.setBusinessType(BUSINESS_TYPE);
        log.setOrderSn(orderSn);
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
                request = buildRequest(rows, validationErrors);
            }
            catch (Exception e)
            {
                validationErrors.add("组装请求失败：" + safeMessage(e));
            }
        }
        if (!validationErrors.isEmpty())
        {
            String message = String.join("；", validationErrors);
            finishFailed(log, startedAt, "VALIDATION", "EXCEL_VALIDATION",
                    message, null, null, request, 0);
            return ProcessResult.failed(orderSn, "VALIDATION", "EXCEL_VALIDATION", message);
        }

        Map<String, Object> response = null;
        Exception lastException = null;
        int attempts = 0;
        for (int attempt = 1; attempt <= MAX_ATTEMPTS; attempt++)
        {
            attempts = attempt;
            try
            {
                response = gatewayService.post(UPDATE_API, request);
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
            return ProcessResult.failed(orderSn, "API_EXCEPTION",
                    lastException.getClass().getSimpleName(), message);
        }

        if (isSuccess(response))
        {
            LocalDateTime successAt = LocalDateTime.now();
            log.setStatus("SUCCESS");
            log.setErrorStage(null);
            log.setErrorCode(valueText(response.get("code")));
            log.setErrorMessage(valueText(response.get("message")));
            log.setRequestId(valueText(response.get("request_id")));
            log.setLingxingResponseTime(valueText(response.get("response_time")));
            log.setAttemptCount(attempts);
            log.setRequestBody(toJson(request));
            log.setResponseBody(toJson(response));
            log.setSuccessTime(successAt);
            log.setDurationMs(Duration.between(startedAt, successAt).toMillis());
            logMapper.updateResult(log);
            return ProcessResult.success(orderSn);
        }

        String code = response == null ? "EMPTY_RESPONSE" : valueText(response.get("code"));
        String message = response == null ? "领星接口返回空响应"
                : firstText(valueText(response.get("message")), valueText(response.get("error_details")),
                        "领星接口返回失败");
        finishFailed(log, startedAt, "LINGXING_API", code, message,
                null, response, request, attempts);
        return ProcessResult.failed(orderSn, "LINGXING_API", code, message);
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
                    throw new IllegalArgumentException("单次最多允许 " + MAX_ROWS + " 行数据");
            }
            if (rows.isEmpty()) throw new IllegalArgumentException("Sheet1 中没有可导入的数据行");
            return rows;
        }
    }

    private void validateHeader(
            Sheet sheet, DataFormatter formatter, FormulaEvaluator evaluator)
    {
        Row header = sheet.getRow(0);
        if (header == null) throw new IllegalArgumentException("Sheet1 第一行表头为空");
        List<String> actual = new ArrayList<>();
        for (int col = 0; col < COLUMN_COUNT; col++)
            actual.add(cellText(header.getCell(col), formatter, evaluator));
        List<String> errors = new ArrayList<>();
        for (int col = 0; col < COLUMN_COUNT; col++)
        {
            if (!EXPECTED_HEADERS.get(col).equals(actual.get(col)))
                errors.add(columnName(col) + "列应为“" + EXPECTED_HEADERS.get(col)
                        + "”，实际为“" + actual.get(col) + "”");
        }
        if (!errors.isEmpty())
            throw new IllegalArgumentException("模板表头不匹配：" + String.join("；", errors));
    }

    private Map<String, List<ExcelRow>> groupRows(List<ExcelRow> rows)
    {
        Map<String, List<ExcelRow>> grouped = new LinkedHashMap<>();
        for (ExcelRow row : rows)
        {
            String orderSn = trim(row.value(0));
            String key = StringUtils.hasText(orderSn) ? orderSn : "__ROW_" + row.rowNo;
            grouped.computeIfAbsent(key, unused -> new ArrayList<>()).add(row);
        }
        return grouped;
    }

    private List<String> validateRows(List<ExcelRow> rows)
    {
        List<String> errors = new ArrayList<>();
        for (ExcelRow row : rows)
        {
            String prefix = "第" + row.rowNo + "行";
            required(row, 0, "发货单号", prefix, errors);
            requiredInteger(row, 1, "物流商id", prefix, errors);
            requiredInteger(row, 2, "物流渠道商id", prefix, errors);
            Integer transportType = requiredInteger(row, 3, "运输类型", prefix, errors);
            Integer orderType = optionalInteger(row, 4, "单号类型", prefix, errors);
            validateTransportOrderType(prefix, transportType, orderType, errors);

            requiredAmount(row, 6, "预估费用单价", prefix, errors);
            required(row, 7, "预估费用单价币种", prefix, errors);
            requiredAmount(row, 8, "预估物流费用", prefix, errors);
            required(row, 9, "预估物流费用币种", prefix, errors);
            validateOtherFee(row, 11, 12, 13, "预估费用其他费", prefix, errors);

            requiredAmount(row, 14, "实际税费", prefix, errors);
            required(row, 15, "实际税费币种", prefix, errors);
            requiredAmount(row, 16, "实际实重", prefix, errors);
            requiredAmount(row, 17, "实际体积", prefix, errors);
            requiredAmount(row, 18, "实际费用单价", prefix, errors);
            required(row, 19, "实际费用单价币种", prefix, errors);
            requiredAmount(row, 20, "实际物流费用", prefix, errors);
            required(row, 21, "实际物流费用币种", prefix, errors);
            validateOtherFee(row, 23, 24, 25, "实际费用其他费", prefix, errors);

            required(row, 26, "物流商单号", prefix, errors);
            required(row, 27, "跟踪号", prefix, errors);
        }
        validateSameOrderSn(rows, errors);
        validateConsistent(rows, errors);
        return errors;
    }

    private void validateTransportOrderType(
            String prefix, Integer transportType, Integer orderType, List<String> errors)
    {
        if (transportType == null) return;
        if (transportType == 4)
        {
            if (orderType != null) errors.add(prefix + "运输类型为4其他时，单号类型必须留空");
            return;
        }
        if (orderType == null)
        {
            errors.add(prefix + "缺少单号类型");
            return;
        }
        boolean valid = (transportType == 1 && orderType == 5)
                || (transportType == 2 && Set.of(1, 2, 3, 4).contains(orderType))
                || (transportType == 3 && Set.of(2, 6).contains(orderType));
        if (!valid) errors.add(prefix + "运输类型与单号类型组合不符合领星规则");
    }

    private void validateSameOrderSn(List<ExcelRow> rows, List<String> errors)
    {
        Set<String> values = new LinkedHashSet<>();
        for (ExcelRow row : rows)
            if (StringUtils.hasText(trim(row.value(0)))) values.add(trim(row.value(0)));
        if (values.size() > 1) errors.add("同一组中存在不同发货单号：" + values);
    }

    private void validateConsistent(List<ExcelRow> rows, List<String> errors)
    {
        int[] scalarColumns = {
                1, 2, 3, 4, 5, 6, 7, 8, 9, 10,
                14, 15, 16, 17, 18, 19, 20, 21, 22, 26, 27
        };
        for (int col : scalarColumns)
        {
            Set<String> values = new LinkedHashSet<>();
            for (ExcelRow row : rows)
            {
                String value = trim(row.value(col));
                if (StringUtils.hasText(value)) values.add(value);
            }
            if (values.size() > 1)
                errors.add("同一发货单的“" + EXPECTED_HEADERS.get(col)
                        + "”存在多个不同值：" + values);
        }
    }

    private Map<String, Object> buildRequest(
            List<ExcelRow> rows, List<String> errors)
    {
        ExcelRow first = rows.get(0);
        Map<String, Object> item = new LinkedHashMap<>();
        item.put("order_sn", trim(first.value(0)));
        item.put("tax_fee_type", 3);
        item.put("logistics_provider_id", integerValue(first.value(1)));
        item.put("logistics_channel_id", integerValue(first.value(2)));
        item.put("logistics_list_type", 1);

        Map<String, Object> tracking = new LinkedHashMap<>();
        tracking.put("transport_type", integerValue(first.value(3)));
        Integer orderType = integerValue(first.value(4));
        if (orderType != null) tracking.put("order_type_code", orderType);

        Map<String, Object> estimateExpenses = new LinkedHashMap<>();
        putIfNotBlank(estimateExpenses, "chargeable_weight", first.value(5));
        putIfNotBlank(estimateExpenses, "price", first.value(6));
        putIfNotBlank(estimateExpenses, "price_currency", currency(first.value(7)));
        putIfNotBlank(estimateExpenses, "logistics_fee", first.value(8));
        putIfNotBlank(estimateExpenses, "logistics_fee_currency", currency(first.value(9)));
        putIfNotBlank(estimateExpenses, "remark", first.value(10));
        estimateExpenses.put("other_fee_arr", buildOtherFees(rows, 11, 12, 13));

        Map<String, Object> actualExpenses = new LinkedHashMap<>();
        putIfNotBlank(actualExpenses, "tax_fee", first.value(14));
        putIfNotBlank(actualExpenses, "tax_fee_currency", currency(first.value(15)));
        putIfNotBlank(actualExpenses, "weight", first.value(16));
        putIfNotBlank(actualExpenses, "volume", first.value(17));
        putIfNotBlank(actualExpenses, "price", first.value(18));
        putIfNotBlank(actualExpenses, "price_currency", currency(first.value(19)));
        putIfNotBlank(actualExpenses, "logistics_fee", first.value(20));
        putIfNotBlank(actualExpenses, "logistics_fee_currency", currency(first.value(21)));
        putIfNotBlank(actualExpenses, "remark", first.value(22));
        actualExpenses.put("other_fee_arr", buildOtherFees(rows, 23, 24, 25));

        Map<String, Object> headLogistics = new LinkedHashMap<>();
        headLogistics.put("tracking_list", List.of(tracking));
        headLogistics.put("estimate_expenses_list", estimateExpenses);
        headLogistics.put("actual_expenses_list", actualExpenses);
        item.put("head_logistics_list", headLogistics);

        List<Map<String, Object>> logisticsList = new ArrayList<>();
        Set<String> logisticsKeys = new LinkedHashSet<>();
        for (ExcelRow row : rows)
        {
            String trackingNumber = trim(row.value(26));
            String replaceTrackingNumber = trim(row.value(27));
            String key = trackingNumber + "|" + replaceTrackingNumber;
            if (!logisticsKeys.add(key)) continue;
            Map<String, Object> logistics = new LinkedHashMap<>();
            putIfNotBlank(logistics, "tracking_number", trackingNumber);
            putIfNotBlank(logistics, "replace_tracking_number", replaceTrackingNumber);
            logisticsList.add(logistics);
        }
        item.put("logistics_list", logisticsList);

        Map<String, Object> request = new LinkedHashMap<>();
        request.put("data", List.of(item));
        return request;
    }

    private List<Map<String, Object>> buildOtherFees(
            List<ExcelRow> rows, int idCol, int amountCol, int currencyCol)
    {
        List<Map<String, Object>> result = new ArrayList<>();
        Set<String> keys = new LinkedHashSet<>();
        for (ExcelRow row : rows)
        {
            String id = trim(row.value(idCol));
            String amount = trim(row.value(amountCol));
            String feeCurrency = currency(row.value(currencyCol));
            if (!StringUtils.hasText(id)
                    && !StringUtils.hasText(amount)
                    && !StringUtils.hasText(feeCurrency))
                continue;
            String key = id + "|" + amount + "|" + feeCurrency;
            if (!keys.add(key)) continue;
            Map<String, Object> fee = new LinkedHashMap<>();
            fee.put("fee_type_id", id);
            fee.put("other_amount", amount);
            fee.put("other_currency", feeCurrency);
            result.add(fee);
        }
        return result;
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
        log.setRequestId(response == null ? null : valueText(response.get("request_id")));
        log.setLingxingResponseTime(
                response == null ? null : valueText(response.get("response_time")));
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

    private boolean isSuccess(Map<String, Object> response)
    {
        if (response == null) return false;
        Object code = response.get("code");
        return (code instanceof Number && ((Number) code).intValue() == 0)
                || "0".equals(valueText(code));
    }

    private boolean isRetryable(Map<String, Object> response)
    {
        if (response == null) return true;
        String code = valueText(response.get("code"));
        String message = valueText(response.get("message")).toLowerCase(Locale.ROOT);
        return "429".equals(code) || message.contains("频繁") || message.contains("限流")
                || message.contains("timeout") || message.contains("超时");
    }

    private void required(
            ExcelRow row, int col, String label, String prefix, List<String> errors)
    {
        if (!StringUtils.hasText(trim(row.value(col))))
            errors.add(prefix + "缺少" + label);
    }

    private void requiredAmount(
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
            if (new BigDecimal(value.replace(",", "")).signum() < 0)
                errors.add(prefix + label + "不能小于0");
        }
        catch (NumberFormatException e)
        {
            errors.add(prefix + label + "不是有效数字：" + value);
        }
    }

    private Integer requiredInteger(
            ExcelRow row, int col, String label, String prefix, List<String> errors)
    {
        String value = trim(row.value(col));
        if (!StringUtils.hasText(value))
        {
            errors.add(prefix + "缺少" + label);
            return null;
        }
        Integer parsed = integerValue(value);
        if (parsed == null || parsed <= 0)
        {
            errors.add(prefix + label + "必须为正整数：" + value);
            return null;
        }
        return parsed;
    }

    private Integer optionalInteger(
            ExcelRow row, int col, String label, String prefix, List<String> errors)
    {
        String value = trim(row.value(col));
        if (!StringUtils.hasText(value)) return null;
        Integer parsed = integerValue(value);
        if (parsed == null || parsed <= 0)
        {
            errors.add(prefix + label + "必须为正整数：" + value);
            return null;
        }
        return parsed;
    }

    private void validateOtherFee(
            ExcelRow row, int idCol, int amountCol, int currencyCol,
            String label, String prefix, List<String> errors)
    {
        String id = trim(row.value(idCol));
        String amount = trim(row.value(amountCol));
        String feeCurrency = trim(row.value(currencyCol));
        boolean hasId = StringUtils.hasText(id);
        boolean hasAmount = StringUtils.hasText(amount);
        boolean hasCurrency = StringUtils.hasText(feeCurrency);
        if (!hasId && !hasAmount && !hasCurrency) return;
        if (!hasId) errors.add(prefix + label + "缺少其他费id");
        if (!hasCurrency) errors.add(prefix + label + "缺少其他费币种");
        if (!hasAmount)
        {
            errors.add(prefix + label + "缺少其他费金额");
            return;
        }
        try
        {
            if (new BigDecimal(amount.replace(",", "")).signum() < 0)
                errors.add(prefix + label + "金额不能小于0");
        }
        catch (NumberFormatException e)
        {
            errors.add(prefix + label + "金额不是有效数字：" + amount);
        }
    }

    private String scalar(List<ExcelRow> rows, int col)
    {
        for (ExcelRow row : rows)
        {
            String value = trim(row.value(col));
            if (StringUtils.hasText(value)) return value;
        }
        return "";
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
            throw new IllegalArgumentException("请选择要上传的 Excel 文件");
        if (file.getSize() > MAX_FILE_SIZE)
            throw new IllegalArgumentException("Excel 文件不能超过20MB");
        String name = file.getOriginalFilename();
        String lower = name == null ? "" : name.toLowerCase(Locale.ROOT);
        if (!lower.endsWith(".xlsx") && !lower.endsWith(".xls"))
            throw new IllegalArgumentException("仅支持 .xlsx 或 .xls 文件");
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
        return "SFI" + LocalDateTime.now().format(BATCH_TIME)
                + UUID.randomUUID().toString().replace("-", "").substring(0, 6).toUpperCase(Locale.ROOT);
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

    private String normalizeEndTime(String endTime)
    {
        String value = trim(endTime);
        if (!StringUtils.hasText(value)) return null;
        return value.length() == 10 ? value + " 23:59:59" : value;
    }

    private String columnName(int index)
    {
        StringBuilder result = new StringBuilder();
        int value = index + 1;
        while (value > 0)
        {
            value--;
            result.insert(0, (char) ('A' + value % 26));
            value /= 26;
        }
        return result.toString();
    }

    private String currency(String value)
    {
        return trim(value).toUpperCase(Locale.ROOT);
    }

    private Integer integerValue(String value)
    {
        String text = trim(value);
        if (!StringUtils.hasText(text)) return null;
        try { return new BigDecimal(text).intValueExact(); }
        catch (Exception ignored) { return null; }
    }

    private String defaultOperator(String operator)
    {
        return StringUtils.hasText(trim(operator)) ? trim(operator) : "unknown";
    }

    private String valueText(Object value)
    {
        return value == null ? "" : String.valueOf(value);
    }

    private void putIfNotBlank(Map<String, Object> target, String key, String value)
    {
        String normalized = trim(value);
        if (!normalized.isEmpty())
        {
            target.put(key, normalized);
        }
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

    private void pauseBetweenRequests()
    {
        sleepQuietly(REQUEST_INTERVAL_MS);
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
        final String orderSn;
        final String errorStage;
        final String errorCode;
        final String errorMessage;

        private ProcessResult(
                boolean success, String orderSn, String errorStage,
                String errorCode, String errorMessage)
        {
            this.success = success;
            this.orderSn = orderSn;
            this.errorStage = errorStage;
            this.errorCode = errorCode;
            this.errorMessage = errorMessage;
        }

        static ProcessResult success(String orderSn)
        {
            return new ProcessResult(true, orderSn, null, null, null);
        }

        static ProcessResult failed(
                String orderSn, String errorStage, String errorCode, String errorMessage)
        {
            return new ProcessResult(false, orderSn, errorStage, errorCode, errorMessage);
        }
    }
}
