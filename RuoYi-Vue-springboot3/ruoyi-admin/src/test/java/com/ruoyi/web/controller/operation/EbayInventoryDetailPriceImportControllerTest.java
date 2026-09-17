package com.ruoyi.web.controller.operation;

import com.ruoyi.common.annotation.Log;
import com.ruoyi.common.enums.BusinessType;
import com.ruoyi.system.service.operation.ebay.EbayInventoryDetailPythonClient;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.multipart.MultipartFile;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

class EbayInventoryDetailPriceImportControllerTest
{
    private static final String ROUTE = "/finance/ebay-inventory-detail/prices/import";

    @AfterEach
    void clearSecurityContext() { SecurityContextHolder.clearContext(); }

    @Test
    void priceImportUsesExistingImportPermissionAndAudit() throws Exception
    {
        var method = EbayInventoryDetailController.class.getMethod("importPrices", MultipartFile.class, String.class);
        assertEquals("@ss.hasPermi('operations:ebayInventoryDetail:import')",
                method.getAnnotation(PreAuthorize.class).value());
        assertArrayEquals(new String[] { "/prices/import" }, method.getAnnotation(PostMapping.class).value());
        assertEquals("Ebay库存明细产品单价导入", method.getAnnotation(Log.class).title());
        assertEquals(BusinessType.IMPORT, method.getAnnotation(Log.class).businessType());
    }

    @Test
    void historyImportUsesAuthenticatedUserAndImportPermission() throws Exception
    {
        var method = EbayInventoryDetailController.class.getMethod("importHistory", MultipartFile.class, String.class);
        assertEquals("@ss.hasPermi('operations:ebayInventoryDetail:import')", method.getAnnotation(PreAuthorize.class).value());
        assertEquals(BusinessType.IMPORT, method.getAnnotation(Log.class).businessType());
        var client = mock(EbayInventoryDetailPythonClient.class);
        when(client.importHistory(any(), eq("actual-user"), eq("history-test")))
                .thenReturn(Map.of("code", 0, "data", Map.of("imported_rows", 75590)));
        var controller = new EbayInventoryDetailController(client)
        {
            @Override public String getUsername() { return "actual-user"; }
        };
        var file = new MockMultipartFile("file", "history.xlsx", "application/octet-stream", new byte[] { 80, 75 });
        MockMvcBuilders.standaloneSetup(controller).build()
                .perform(multipart("/finance/ebay-inventory-detail/history/import").file(file)
                        .param("operator", "forged-user").header("X-Request-ID", "history-test"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.data.imported_rows").value(75590));
        verify(client).importHistory(file, "actual-user", "history-test");
        verifyNoMoreInteractions(client);
    }

    @Test
    void multipartImportUsesAuthenticatedOperatorUnwrapsResultAndNeverRecalculates() throws Exception
    {
        var client = mock(EbayInventoryDetailPythonClient.class);
        var file = new MockMultipartFile("file", "prices.xlsx", "application/octet-stream", new byte[] { 80, 75 });
        Map<String, Object> data = Map.of("imported_rows", 3, "duplicate_rows", 2, "sku_count", 2,
                "middle_code_count", 1, "skipped_rows", 0, "warnings", List.of());
        when(client.importPrices(any(), eq("actual-user"), eq("price-trace")))
                .thenReturn(Map.of("code", 0, "data", data));
        var controller = new EbayInventoryDetailController(client)
        {
            @Override public String getUsername() { return "actual-user"; }
        };
        var mvc = MockMvcBuilders.standaloneSetup(controller).build();

        mvc.perform(multipart(ROUTE).file(file).param("operator", "forged-user")
                        .param("statDate", "2000-01-01").header("X-Request-ID", "price-trace"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.code").value(200))
                .andExpect(jsonPath("$.data.imported_rows").value(3))
                .andExpect(jsonPath("$.data.duplicate_rows").value(2))
                .andExpect(jsonPath("$.data.sku_count").value(2));
        verify(client).importPrices(file, "actual-user", "price-trace");
        verifyNoMoreInteractions(client);
    }

    @Test
    void getOrMissingFileCannotImport() throws Exception
    {
        var client = mock(EbayInventoryDetailPythonClient.class);
        var mvc = MockMvcBuilders.standaloneSetup(new EbayInventoryDetailController(client)).build();
        mvc.perform(get(ROUTE)).andExpect(status().isMethodNotAllowed());
        mvc.perform(multipart(ROUTE)).andExpect(status().isBadRequest());
        verifyNoInteractions(client);
    }

    @Test
    void listOrExportPermissionCannotImportPrices()
    {
        try (var context = new AnnotationConfigApplicationContext(SecurityConfig.class))
        {
            SecurityContextHolder.getContext().setAuthentication(
                    new UsernamePasswordAuthenticationToken("test-user", "unused", List.of()));
            var controller = context.getBean(EbayInventoryDetailController.class);
            var permissions = context.getBean(TestPermissionService.class);
            var file = new MockMultipartFile("file", new byte[] { 80, 75 });
            for (String permission : List.of("", "operations:ebayInventoryDetail:list", "operations:ebayInventoryDetail:export"))
            {
                permissions.allowed = permission;
                assertThrows(AccessDeniedException.class, () -> controller.importPrices(file, null));
                assertThrows(AccessDeniedException.class, () -> controller.importHistory(file, null));
            }
            verifyNoInteractions(context.getBean(EbayInventoryDetailPythonClient.class));
        }
    }

    @Configuration
    @EnableMethodSecurity
    static class SecurityConfig
    {
        @Bean EbayInventoryDetailPythonClient client() { return mock(EbayInventoryDetailPythonClient.class); }
        @Bean EbayInventoryDetailController controller(EbayInventoryDetailPythonClient client)
        {
            return new EbayInventoryDetailController(client);
        }
        @Bean(name = "ss") TestPermissionService permissions() { return new TestPermissionService(); }
    }

    public static class TestPermissionService
    {
        String allowed;
        public boolean hasPermi(String permission) { return permission.equals(allowed); }
    }
}
