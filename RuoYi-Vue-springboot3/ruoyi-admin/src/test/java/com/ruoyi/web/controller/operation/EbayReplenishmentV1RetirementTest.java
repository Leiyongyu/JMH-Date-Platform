package com.ruoyi.web.controller.operation;

import com.ruoyi.common.core.domain.entity.SysUser;
import com.ruoyi.common.core.domain.model.LoginUser;
import com.ruoyi.common.core.redis.RedisCache;
import com.ruoyi.system.domain.operation.OperationImportTask;
import com.ruoyi.system.service.operation.OperationImportService;
import com.ruoyi.system.service.operation.ebay.EbayReplenishmentV2ExportService;
import com.ruoyi.system.service.operation.ebay.EbayReplenishmentV2LeadTimeService;
import com.ruoyi.system.service.operation.ebay.EbayReplenishmentV2PythonClient;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

class EbayReplenishmentV1RetirementTest
{
    private MockMvc mvc;
    private OperationImportService importer;
    private RedisCache locks;
    private EbayReplenishmentV2PythonClient client;

    @BeforeEach
    void setup()
    {
        var user = new SysUser();
        user.setUserName("test-operator");
        var login = new LoginUser(25L, 1L, user, Set.of());
        SecurityContextHolder.getContext().setAuthentication(
                new UsernamePasswordAuthenticationToken(login, "unused", List.of()));
        importer = mock(OperationImportService.class);
        locks = mock(RedisCache.class);
        when(locks.tryLock(anyString(), anyLong())).thenReturn(true);
        var tracking = new EbayPriceTrackingController();
        ReflectionTestUtils.setField(tracking, "importService", importer);
        ReflectionTestUtils.setField(tracking, "redisCache", locks);
        client = mock(EbayReplenishmentV2PythonClient.class);
        var v2 = new EbayReplenishmentV2Controller(client,
                mock(EbayReplenishmentV2LeadTimeService.class), new EbayReplenishmentV2ExportService());
        mvc = MockMvcBuilders.standaloneSetup(tracking, v2).build();
    }

    @AfterEach
    void logout() { SecurityContextHolder.clearContext(); }

    @Test
    void retiredEndpointsAreAbsentWhileV2ListAndRefreshStillReachPython() throws Exception
    {
        for (String path : List.of("list", "distinct-values", "formula/list"))
            mvc.perform(get("/operations/ebay/replenishment/" + path)).andExpect(status().isNotFound());
        for (String path : List.of("search", "refresh", "export", "update-product-nature", "formula/update"))
            mvc.perform(post("/operations/ebay/replenishment/" + path)).andExpect(status().isNotFound());
        when(client.list(anyMap(), any())).thenReturn(Map.of("data", Map.of("items", List.of(), "total", 0)));
        mvc.perform(get("/operations/ebay/replenishment-v2/list"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.data.total").value(0));
        mvc.perform(get("/operations/ebay/replenishment-v2/list").param("refresh", "true"))
                .andExpect(status().isOk());
        verify(client).list(argThat(params -> Boolean.TRUE.equals(params.get("refresh"))), any());
    }

    @Test
    void migratedUploadsRetainTheirImporterOperatorAndSharedLock() throws Exception
    {
        when(importer.importEbaySales(any(), anyString())).thenReturn(new OperationImportTask());
        when(importer.importProfitRate(any(), anyString())).thenReturn(new OperationImportTask());
        when(importer.importReturnRate(any(), anyString())).thenReturn(new OperationImportTask());
        for (String path : List.of("import-sales", "import-profit-rate", "import-return-rate"))
        {
            var file = new MockMultipartFile("file", "history.xlsx", "application/octet-stream", new byte[]{1});
            mvc.perform(multipart("/operations/ebay/price-tracking/" + path).file(file))
                    .andExpect(status().isOk()).andExpect(jsonPath("$.code").value(200));
        }
        verify(importer).importEbaySales(any(), eq("test-operator"));
        verify(importer).importProfitRate(any(), eq("test-operator"));
        verify(importer).importReturnRate(any(), eq("test-operator"));
        verify(locks, times(3)).unlock("lock:sync:lingxing:ebay");
        verifyNoInteractions(client);
    }

    @Test
    void busySharedLockPreventsAnyUploadMutation() throws Exception
    {
        when(locks.tryLock(anyString(), anyLong())).thenReturn(false);
        mvc.perform(multipart("/operations/ebay/price-tracking/import-sales")
                .file(new MockMultipartFile("file", "history.xlsx", "application/octet-stream", new byte[]{1})))
                .andExpect(jsonPath("$.code").value(500));
        verifyNoInteractions(importer, client);
        verify(locks, never()).unlock(anyString());
    }
}
