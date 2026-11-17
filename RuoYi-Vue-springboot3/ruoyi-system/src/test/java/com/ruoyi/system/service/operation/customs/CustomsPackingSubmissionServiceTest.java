package com.ruoyi.system.service.operation.customs;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.contains;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.system.domain.operation.customs.CustomsPackingSavedPayload;
import com.ruoyi.system.domain.operation.customs.CustomsPackingSubmission;
import com.ruoyi.system.mapper.operation.customs.CustomsPackingSubmissionMapper;
import com.ruoyi.system.service.operation.external.lingxing.LingxingGatewayService;
import com.ruoyi.system.service.operation.sync.SyncAlertService;
import java.util.List;
import java.util.concurrent.Executor;
import java.util.concurrent.RejectedExecutionException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.AbstractPlatformTransactionManager;
import org.springframework.transaction.support.DefaultTransactionStatus;
import org.springframework.transaction.support.TransactionTemplate;

class CustomsPackingSubmissionServiceTest
{
    private CustomsPackingSubmissionMapper mapper;
    private LingxingGatewayService gateway;
    private SyncAlertService alertService;

    @BeforeEach
    void setUp()
    {
        mapper = mock(CustomsPackingSubmissionMapper.class);
        gateway = mock(LingxingGatewayService.class);
        alertService = mock(SyncAlertService.class);

        CustomsPackingSavedPayload saved = new CustomsPackingSavedPayload();
        saved.setLogId(11L);
        saved.setInboundPlanId("STA-1");
        saved.setShipmentId("SHIP-1");
        saved.setSid(12645L);
        saved.setRequestBody("{\"inboundPlanId\":\"STA-1\",\"shipmentId\":\"SHIP-1\","
                + "\"sid\":12645,\"boxes\":[{\"items\":[]}]}");
        when(mapper.selectLatestSavedPayloads("STA-1")).thenReturn(List.of(saved));
        when(mapper.selectPositionTypeByInboundPlanId("STA-1")).thenReturn(2);
        when(mapper.countExpectedShipments("STA-1")).thenReturn(1);
        when(mapper.insertReady(any())).thenReturn(1);
        when(mapper.claimForSubmit(eq("STA-1"), anyString())).thenReturn(1);

        CustomsPackingSubmission claimed = new CustomsPackingSubmission();
        claimed.setId(21L);
        claimed.setInboundPlanId("STA-1");
        claimed.setStatus("SUBMITTING");
        when(mapper.selectByInboundPlanId("STA-1")).thenReturn(claimed);
    }

    @Test
    void preparedPayloadFailureRollsBackClaimAndDoesNotSubmitTask()
    {
        RecordingTransactionManager transactionManager =
                new RecordingTransactionManager();
        Executor executor = mock(Executor.class);
        when(mapper.updatePrepared(eq(21L), eq(12645L), eq(2), anyString(), anyString()))
                .thenReturn(0);
        CustomsPackingSubmissionService service =
                service(executor, transactionManager);

        assertThatThrownBy(() -> service.submit("STA-1", "tester"))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("装箱提交请求保存失败");

        assertThat(transactionManager.rolledBack).isTrue();
        assertThat(transactionManager.committed).isFalse();
        verify(executor, never()).execute(any());
    }

    @Test
    void rejectedTaskIsRecordedAsRetryableFailureAfterCommittedClaim()
    {
        RecordingTransactionManager transactionManager =
                new RecordingTransactionManager();
        Executor executor = command -> {
            throw new RejectedExecutionException("queue full");
        };
        when(mapper.updatePrepared(eq(21L), eq(12645L), eq(2), anyString(), anyString()))
                .thenReturn(1);
        when(mapper.updateAfterSubmit(any(), any(), any(), any(), any(), any()))
                .thenReturn(1);
        CustomsPackingSubmissionService service =
                service(executor, transactionManager);

        assertThatThrownBy(() -> service.submit("STA-1", "tester"))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("领星接口尚未调用");

        assertThat(transactionManager.committed).isTrue();
        assertThat(transactionManager.rolledBack).isFalse();
        verify(mapper).updateAfterSubmit(
                eq(21L), eq("FAILED"), isNull(), isNull(), isNull(),
                contains("后台任务提交失败"));
    }

    private CustomsPackingSubmissionService service(
            Executor executor, RecordingTransactionManager transactionManager)
    {
        return new CustomsPackingSubmissionService(
                mapper, gateway, new ObjectMapper(), executor, alertService,
                new TransactionTemplate(transactionManager));
    }

    private static class RecordingTransactionManager
            extends AbstractPlatformTransactionManager
    {
        private boolean committed;
        private boolean rolledBack;

        @Override
        protected Object doGetTransaction()
        {
            return new Object();
        }

        @Override
        protected void doBegin(Object transaction, TransactionDefinition definition)
        {
        }

        @Override
        protected void doCommit(DefaultTransactionStatus status)
        {
            committed = true;
        }

        @Override
        protected void doRollback(DefaultTransactionStatus status)
        {
            rolledBack = true;
        }
    }
}
