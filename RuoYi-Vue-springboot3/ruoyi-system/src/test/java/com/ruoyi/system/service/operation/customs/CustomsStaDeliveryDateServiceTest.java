package com.ruoyi.system.service.operation.customs;

import com.ruoyi.system.service.operation.external.lingxing.LingxingGatewayService;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class CustomsStaDeliveryDateServiceTest
{
    private static final String PLAN_API = "amzStaServer/openapi/inbound-plan/page";
    private static final String DATE_API = "amzStaServer/openapi/inbound-shipment/getDeliveryDateList";
    private LingxingGatewayService gateway;
    private CustomsStaDeliveryDateService service;

    @BeforeEach
    void setup()
    {
        gateway = mock(LingxingGatewayService.class);
        service = new CustomsStaDeliveryDateService(gateway);
    }

    @Test
    void fbaNumberResolvesByExactPlanAndSidThenQueriesOptionsWithoutSaving() throws Exception
    {
        when(gateway.post(eq(PLAN_API), anyMap())).thenReturn(Map.of("code", 0, "data", Map.of("records", List.of(
                record("other-plan", 12616, "wrong-plan"), record("plan-1", 999, "wrong-sid"),
                record("plan-1", 12616, "sh-internal")))));
        var options = List.of(Map.of("deliveryWindowOptionId", "dw-1", "startDate", "2026-10-25",
                "endDate", "2026-10-31", "validUntil", "2027-01-02"));
        var response = Map.<String, Object>of("code", 0, "requestId", "trace-1", "data", Map.of(
                "inboundPlanId", "plan-1", "shipmentId", "sh-internal", "shipmentList", options));
        when(gateway.post(eq(DATE_API), anyMap())).thenReturn(response);
        var result = service.query(" plan-1 ", " FBA15MPTRK38 ", 12616L);
        assertThat(result).containsEntry("success", true).containsEntry("shipmentNo", "FBA15MPTRK38")
                .containsEntry("shipmentId", "sh-internal").containsEntry("optionCount", 1)
                .containsEntry("options", options).containsEntry("response", response);
        verify(gateway).post(eq(PLAN_API), argThat(body -> body.get("shipmentIdList").equals(List.of("FBA15MPTRK38"))));
        verify(gateway).post(DATE_API, Map.of("inboundPlanId", "plan-1", "shipmentId", "sh-internal", "sid", 12616L));
        verifyNoMoreInteractions(gateway);
    }

    @Test
    void internalIdIsPassedDirectlyAndEmptyOptionsAreNotAFailure() throws Exception
    {
        when(gateway.post(eq(DATE_API), anyMap())).thenReturn(Map.of("code", 0, "data", Map.of("shipmentList", List.of())));
        assertThat(service.query("plan-1", "sh-1", 12616L))
                .containsEntry("success", true).containsEntry("optionCount", 0).containsEntry("message", "暂无可选送达时间");
        verify(gateway).post(DATE_API, Map.of("inboundPlanId", "plan-1", "shipmentId", "sh-1", "sid", 12616L));
        verifyNoMoreInteractions(gateway);
    }

    @Test
    void businessErrorsPreserveOriginalResponseAndRequestId() throws Exception
    {
        var response = Map.<String, Object>of("code", -1, "message", "查询不到对应的货件shipment数据", "requestId", "trace-failed");
        when(gateway.post(anyString(), anyMap())).thenReturn(response);
        var result = service.query("plan-1", "sh-1", 12616L);
        assertThat(result).containsEntry("success", false).containsEntry("response", response);
        assertThat(result.get("message").toString()).contains("code=-1", "查询不到对应的货件shipment数据", "trace-failed");
    }

    @Test
    void mismatchedOrAmbiguousAssociationDoesNotQueryDeliveryDates() throws Exception
    {
        when(gateway.post(eq(PLAN_API), anyMap())).thenReturn(Map.of("code", 0, "data", Map.of("records", List.of(record("wrong-plan", 12616, "sh-1")))));
        assertThatThrownBy(() -> service.query("plan-1", "FBA15MPTRK38", 12616L)).hasMessageContaining("未找到");
        verify(gateway, never()).post(eq(DATE_API), anyMap());
    }

    @Test
    void multipleDistinctInternalIdsAreRejected() throws Exception
    {
        when(gateway.post(eq(PLAN_API), anyMap())).thenReturn(Map.of("code", 0, "data", Map.of("records", List.of(
                record("plan-1", 12616, "sh-1"), record("plan-1", 12616, "sh-2")))));
        assertThatThrownBy(() -> service.query("plan-1", "FBA15MPTRK38", 12616L)).hasMessageContaining("多个shipmentId");
        verify(gateway, never()).post(eq(DATE_API), anyMap());
    }

    @Test
    void invalidInputsNeverCallLingxing()
    {
        assertThatThrownBy(() -> service.query("", "sh-1", 1L)).hasMessageContaining("STA任务编号不能为空");
        assertThatThrownBy(() -> service.query("plan-1", "", 1L)).hasMessageContaining("货件单号不能为空");
        assertThatThrownBy(() -> service.query("plan-1", "sh-1", 0L)).hasMessageContaining("SID");
        assertThatThrownBy(() -> service.query("plan-1", "sh-1", null)).hasMessageContaining("SID");
        verifyNoInteractions(gateway);
    }

    @Test
    void wrongReturnedContextOrMalformedSuccessDoesNotBecomeAnEmptySuccess() throws Exception
    {
        when(gateway.post(eq(DATE_API), anyMap())).thenReturn(Map.of("code", 0, "data", Map.of("shipmentId", "another-shipment", "shipmentList", List.of())));
        assertThatThrownBy(() -> service.query("plan-1", "sh-1", 12616L)).hasMessageContaining("不一致");
        service = new CustomsStaDeliveryDateService(gateway);
        when(gateway.post(eq(DATE_API), anyMap())).thenReturn(Map.of("code", 0, "data", Map.of()));
        assertThatThrownBy(() -> service.query("plan-1", "sh-1", 12616L)).hasMessageContaining("缺少可选送达时间列表");
    }

    private Map<String, Object> record(String plan, int sid, String shipmentId)
    {
        return Map.of("inboundPlanId", plan, "sid", sid, "shipmentList", List.of(
                Map.of("shipmentConfirmationId", "FBA15MPTRK38", "shipmentId", shipmentId)));
    }
}
