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
import com.ruoyi.system.mapper.operation.customs.CustomsShipmentFeeImportBatchMapper;
import com.ruoyi.system.mapper.operation.customs.CustomsShipmentFeeImportLogMapper;
import com.ruoyi.system.mapper.operation.external.LingxingLogisticsChannelMapper;
import com.ruoyi.system.mapper.operation.external.LingxingShipmentOrderMappingMapper;
import com.ruoyi.system.service.operation.external.lingxing.LingxingGatewayService;
import java.io.ByteArrayOutputStream;
import java.util.List;
import java.util.Map;
import java.util.concurrent.Executor;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.atomic.AtomicReference;
import org.apache.poi.ss.usermodel.Row;
import org.apache.poi.ss.usermodel.Sheet;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockMultipartFile;

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
