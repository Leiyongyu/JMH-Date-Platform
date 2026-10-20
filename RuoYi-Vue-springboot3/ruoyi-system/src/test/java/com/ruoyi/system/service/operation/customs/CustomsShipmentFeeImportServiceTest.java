package com.ruoyi.system.service.operation.customs;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.system.domain.operation.customs.CustomsShipmentFeeImportBatch;
import com.ruoyi.system.domain.operation.customs.CustomsShipmentFeeImportLog;
import com.ruoyi.system.mapper.operation.customs.CustomsShipmentFeeImportBatchMapper;
import com.ruoyi.system.mapper.operation.customs.CustomsShipmentFeeImportLogMapper;
import com.ruoyi.system.mapper.operation.external.LingxingLogisticsChannelMapper;
import com.ruoyi.system.mapper.operation.external.LingxingShipmentOrderMappingMapper;
import com.ruoyi.system.service.operation.external.lingxing.LingxingGatewayService;
import java.io.ByteArrayOutputStream;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.concurrent.Executor;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.atomic.AtomicReference;
import org.apache.poi.ss.usermodel.Row;
import org.apache.poi.ss.usermodel.Sheet;
import org.apache.poi.ss.usermodel.Workbook;
import org.apache.poi.hssf.usermodel.HSSFWorkbook;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockMultipartFile;
import org.mockito.ArgumentCaptor;

class CustomsShipmentFeeImportServiceTest
{
    private static final List<String> HEADERS = List.of(
            "货件单号", "物流商", "渠道商", "运输类型", "单号类型",
            "费用明细-预估费用", "单价", "单价币种", "物流费用", "物流费用币种",
            "预估费用备注", "预估费用-其他费id", "其他费金额", "其他费币种",
            "费用明细-实际费用", "税费币种", "实重（单位：KG）", "体积（单位：m³）",
            "单价", "单价币种", "物流费用", "物流费用币种", "实际费用备注",
            "实际费用-其他费id", "其他费金额", "其他费币种", "物流商单号", "跟踪号");

    private CustomsShipmentFeeImportBatchMapper batchMapper;
    private CustomsShipmentFeeImportLogMapper logMapper;
    private LingxingLogisticsChannelMapper channelMapper;
    private LingxingShipmentOrderMappingMapper mappingMapper;
    private LingxingGatewayService gateway;

    @BeforeEach
    void setUp()
    {
        batchMapper = mock(CustomsShipmentFeeImportBatchMapper.class);
        logMapper = mock(CustomsShipmentFeeImportLogMapper.class);
        channelMapper = mock(LingxingLogisticsChannelMapper.class);
        mappingMapper = mock(LingxingShipmentOrderMappingMapper.class);
        gateway = mock(LingxingGatewayService.class);
        when(batchMapper.insert(any())).thenAnswer(invocation -> {
            CustomsShipmentFeeImportBatch batch = invocation.getArgument(0);
            batch.setId(101L);
            return 1;
        });
        when(batchMapper.updateResult(any())).thenReturn(1);
    }

    @Test
    void importReturnsQueuedBatchBeforeAnyLingxingRequest() throws Exception
    {
        AtomicReference<Runnable> submitted = new AtomicReference<>();
        Executor executor = submitted::set;
        CustomsShipmentFeeImportService service = service(executor);

        Map<String, Object> result = service.importFile(workbook(), "tester");

        assertThat(result)
                .containsEntry("businessType", "SHIPMENT_LOGISTICS")
                .containsEntry("batchId", 101L)
                .containsEntry("status", "QUEUED")
                .containsEntry("totalShipments", 1);
        assertThat(submitted.get()).isNotNull();
        verify(gateway, never()).post(any(), any());
    }

    @Test
    void rejectedBackgroundTaskMarksBatchFailedAndReportsBatchNumber() throws Exception
    {
        Executor executor = command -> {
            throw new RejectedExecutionException("queue full");
        };
        CustomsShipmentFeeImportService service = service(executor);

        assertThatThrownBy(() -> service.importFile(workbook(), "tester"))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("后台任务提交失败")
                .hasMessageContaining("SFI");

        verify(gateway, never()).post(any(), any());
        verify(batchMapper).insert(any());
        verify(batchMapper, org.mockito.Mockito.atLeast(2)).updateResult(any());
    }

    @Test
    void renamedHeadersProduceExactlyTheSameLingxingPayload() throws Exception
    {
        when(mappingMapper.selectShipmentSnByShipmentId("FBA-TEST-001")).thenReturn("SP-TEST-001");
        when(channelMapper.countAll()).thenReturn(1);
        when(channelMapper.countByIdAndProvider(101L, 202L)).thenReturn(1);
        when(gateway.post(any(), any())).thenReturn(Map.of("code", 0));
        List<String> renamed = new ArrayList<>();
        for (int i = 0; i < HEADERS.size(); i++) renamed.add("自定义字段" + i);
        CustomsShipmentFeeImportService service = service(Runnable::run);

        service.importFile(dataWorkbook(HEADERS, validValues(), "Sheet1", false), "tester");
        service.importFile(dataWorkbook(renamed, validValues(), "Sheet1", false), "tester");

        ArgumentCaptor<Map<String, Object>> requests = ArgumentCaptor.forClass(Map.class);
        verify(gateway, org.mockito.Mockito.times(2)).post(
                org.mockito.ArgumentMatchers.eq("erp/sc/routing/storage/shipment/updateListLogistics"),
                requests.capture());
        assertThat(requests.getAllValues().get(1)).isEqualTo(requests.getAllValues().get(0));
        assertThat(requests.getValue()).isEqualTo(Map.of("data", List.of(Map.of(
                "order_sn", "SP-TEST-001", "tax_fee_type", 3,
                "logistics_channel_id", 101, "logistics_provider_id", 202,
                "logistics_list_type", 1,
                "head_logistics_list", Map.of(
                        "tracking_list", List.of(Map.of("transport_type", 2, "order_type_code", 1)),
                        "estimate_expenses_list", Map.of(
                                "chargeable_weight", "12", "price", "13", "price_currency", "USD",
                                "logistics_fee", "14", "logistics_fee_currency", "CNY",
                                "remark", "预估备注", "other_fee_arr", List.of(Map.of(
                                        "fee_type_id", "301", "other_amount", "15", "other_currency", "EUR"))),
                        "actual_expenses_list", Map.of(
                                "tax_fee", "16", "tax_fee_currency", "GBP", "weight", "17", "volume", "18",
                                "price", "19", "price_currency", "EUR", "logistics_fee", "20",
                                "logistics_fee_currency", "USD", "remark", "实际备注",
                                "other_fee_arr", List.of(Map.of(
                                        "fee_type_id", "302", "other_amount", "21", "other_currency", "CNY")))),
                "logistics_list", List.of(Map.of(
                        "tracking_number", "TRACK-001", "replace_tracking_number", "REPLACE-001"))))));
    }

    @Test
    void blankAndDuplicateHeaderNamesAlsoWorkInLegacyXls() throws Exception
    {
        when(mappingMapper.selectShipmentSnByShipmentId("FBA-TEST-001")).thenReturn("SP-TEST-001");
        when(gateway.post(any(), any())).thenReturn(Map.of("code", 0));
        String[] names = new String[28];
        Arrays.fill(names, "任意重复名称");
        names[0] = "";
        names[5] = "";
        names[27] = "";

        service(Runnable::run).importFile(
                dataWorkbook(Arrays.asList(names), validValues(), "Sheet1", true), "tester");

        verify(gateway).post(any(), any());
        ArgumentCaptor<CustomsShipmentFeeImportLog> logs =
                ArgumentCaptor.forClass(CustomsShipmentFeeImportLog.class);
        verify(logMapper).updateResult(logs.capture());
        assertThat(logs.getValue().getStatus()).isEqualTo("SUCCESS");
        assertThat(logs.getValue().getSourceRows()).isEqualTo("2");
    }

    @Test
    void positionalImportStillRejectsMissingAndNegativeAmountsBeforeCallingLingxing() throws Exception
    {
        when(mappingMapper.selectShipmentSnByShipmentId("FBA-TEST-001")).thenReturn("SP-TEST-001");
        String[] values = validValues();
        values[6] = "";
        values[20] = "-1";

        service(Runnable::run).importFile(
                dataWorkbook(HEADERS, values, "Sheet1", false), "tester");

        verify(gateway, never()).post(any(), any());
        ArgumentCaptor<CustomsShipmentFeeImportLog> logs =
                ArgumentCaptor.forClass(CustomsShipmentFeeImportLog.class);
        verify(logMapper).updateResult(logs.capture());
        assertThat(logs.getValue().getStatus()).isEqualTo("FAILED");
        assertThat(logs.getValue().getErrorMessage())
                .contains("缺少预估费用单价", "实际物流费用不能小于0");
    }

    @Test
    void missingSheet1IsStillRejected() throws Exception
    {
        assertThatThrownBy(() -> service(Runnable::run).importFile(
                dataWorkbook(HEADERS, validValues(), "其他工作表", false), "tester"))
                .hasMessageContaining("缺少 Sheet1");
        verify(gateway, never()).post(any(), any());
    }

    @Test
    void missingFirstRowIsRejectedInsteadOfGuessingDataStart() throws Exception
    {
        assertThatThrownBy(() -> service(Runnable::run).importFile(
                dataWorkbook(null, validValues(), "Sheet1", false), "tester"))
                .hasMessageContaining("保留第一行表头");
        verify(gateway, never()).post(any(), any());
    }

    private String[] validValues()
    {
        return new String[] {
                "FBA-TEST-001", "101", "202", "2", "1",
                "12", "13", "usd", "14", "cny", "预估备注", "301", "15", "eur",
                "16", "gbp", "17", "18", "19", "eur", "20", "usd",
                "实际备注", "302", "21", "cny", "TRACK-001", "REPLACE-001"
        };
    }

    private MockMultipartFile dataWorkbook(
            List<String> headers, String[] values, String sheetName, boolean legacy) throws Exception
    {
        try (Workbook workbook = legacy ? new HSSFWorkbook() : new XSSFWorkbook();
             ByteArrayOutputStream output = new ByteArrayOutputStream())
        {
            Sheet sheet = workbook.createSheet(sheetName);
            if (headers != null)
            {
                Row header = sheet.createRow(0);
                for (int i = 0; i < headers.size(); i++)
                    header.createCell(i).setCellValue(headers.get(i));
            }
            Row row = sheet.createRow(1);
            for (int i = 0; i < values.length; i++) row.createCell(i).setCellValue(values[i]);
            workbook.write(output);
            return new MockMultipartFile("file", legacy ? "fee.xls" : "fee.xlsx",
                    "application/octet-stream", output.toByteArray());
        }
    }

    private CustomsShipmentFeeImportService service(Executor executor)
    {
        return new CustomsShipmentFeeImportService(
                batchMapper, logMapper, channelMapper, mappingMapper,
                gateway, new ObjectMapper(), executor);
    }

    private MockMultipartFile workbook() throws Exception
    {
        try (XSSFWorkbook workbook = new XSSFWorkbook();
             ByteArrayOutputStream output = new ByteArrayOutputStream())
        {
            Sheet sheet = workbook.createSheet("Sheet1");
            Row header = sheet.createRow(0);
            for (int i = 0; i < HEADERS.size(); i++)
                header.createCell(i).setCellValue(HEADERS.get(i));
            sheet.createRow(1).createCell(0).setCellValue("SP-TEST-001");
            workbook.write(output);
            return new MockMultipartFile(
                    "file", "shipment-fee.xlsx",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    output.toByteArray());
        }
    }
}
