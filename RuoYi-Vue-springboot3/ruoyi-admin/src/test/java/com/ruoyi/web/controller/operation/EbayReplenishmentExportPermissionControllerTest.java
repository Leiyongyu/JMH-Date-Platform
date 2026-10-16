package com.ruoyi.web.controller.operation;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.common.core.domain.TreeSelect;
import com.ruoyi.common.core.domain.entity.SysDept;
import com.ruoyi.common.core.domain.entity.SysMenu;
import com.ruoyi.common.core.domain.model.LoginUser;
import com.ruoyi.common.exception.ServiceException;
import com.ruoyi.framework.web.service.PermissionService;
import com.ruoyi.system.service.operation.ebay.EbayReplenishmentV2ExportService;
import com.ruoyi.system.service.operation.ebay.EbayReplenishmentV2LeadTimeService;
import com.ruoyi.system.service.operation.ebay.EbayReplenishmentV2PythonClient;
import java.io.ByteArrayInputStream;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

class EbayReplenishmentExportPermissionControllerTest
{
    private static final String LIST = "operations:ebayReplenishmentV2:list";
    private static final String EXPORT = "operations:ebayReplenishmentV2:export";
    private static final String FIELD = EbayReplenishmentV2ExportService.COLUMN_PERMISSION_PREFIX;

    @Test
    void permissionTreeExposesStableBranchIdentityWithoutChangingDepartmentNodes() throws Exception
    {
        var field = new SysMenu();
        field.setMenuId(3L); field.setMenuName("SKU"); field.setPerms(FIELD + "sku");
        var export = new SysMenu();
        export.setMenuId(2L); export.setMenuName("导出"); export.setPerms(EXPORT);
        export.setChildren(List.of(field));
        var page = new SysMenu();
        page.setMenuId(1L); page.setMenuName("eBay补货2.0"); page.setPerms(LIST);
        page.setChildren(List.of(export));
        var mapper = new ObjectMapper();
        var json = mapper.readTree(mapper.writeValueAsString(new TreeSelect(page)));
        assertEquals(EXPORT, json.get("children").get(0).get("perms").asText());
        assertEquals(FIELD + "sku", json.get("children").get(0).get("children").get(0).get("perms").asText());
        var dept = new SysDept();
        dept.setDeptId(9L); dept.setDeptName("测试部门");
        assertFalse(mapper.readTree(mapper.writeValueAsString(new TreeSelect(dept))).has("perms"));
    }

    @Configuration
    @EnableMethodSecurity
    static class Config
    {
        @Bean(name = "ss") PermissionService permissions() { return new PermissionService(); }
        @Bean EbayReplenishmentV2PythonClient client() { return mock(EbayReplenishmentV2PythonClient.class); }
        @Bean EbayReplenishmentV2LeadTimeService leadTime() { return mock(EbayReplenishmentV2LeadTimeService.class); }
        @Bean EbayReplenishmentV2ExportService exporter() { return new EbayReplenishmentV2ExportService(); }
        @Bean EbayReplenishmentV2Controller controller(EbayReplenishmentV2PythonClient client,
                EbayReplenishmentV2LeadTimeService leadTime, EbayReplenishmentV2ExportService exporter)
        {
            return new EbayReplenishmentV2Controller(client, leadTime, exporter);
        }
    }

    private static void login(Set<String> permissions)
    {
        RequestContextHolder.setRequestAttributes(new ServletRequestAttributes(new MockHttpServletRequest()));
        var user = new LoginUser();
        user.setUserId(25L);
        user.setPermissions(permissions);
        SecurityContextHolder.getContext().setAuthentication(
                new UsernamePasswordAuthenticationToken(user, "unused", List.of()));
    }

    @Test
    void listingStillShowsAllFieldsWithoutAnyExportColumnPermission()
    {
        login(Set.of(LIST));
        try (var context = new AnnotationConfigApplicationContext(Config.class))
        {
            var client = context.getBean(EbayReplenishmentV2PythonClient.class);
            var item = Map.of("sku", "BMW-1-2", "gross_profit_amount", 100, "development_note", "页面可见");
            var data = Map.of("items", List.of(item));
            when(client.list(anyMap(), any())).thenReturn(Map.of("data", data));
            var controller = context.getBean(EbayReplenishmentV2Controller.class);
            assertEquals(data, controller.list(null, null, null, null, null, null, 1, 50, null, null, false, false, "trace").get("data"));
        }
        finally { SecurityContextHolder.clearContext(); RequestContextHolder.resetRequestAttributes(); }
    }

    @Test
    void exportNeedsPageAndColumnPermissionsBeforeQueryingPython()
    {
        try (var context = new AnnotationConfigApplicationContext(Config.class))
        {
            var controller = context.getBean(EbayReplenishmentV2Controller.class);
            for (Set<String> denied : List.of(Set.of(FIELD + "sku"), Set.of(LIST),
                    Set.of(LIST, FIELD + "sku"), Set.of(EXPORT, FIELD + "sku")))
            {
                login(denied);
                assertThrows(AccessDeniedException.class, () -> controller.export(null, null, null, null,
                        null, null, null, null, null, "trace", new MockHttpServletResponse()));
            }
            login(Set.of(LIST, EXPORT));
            var response = new MockHttpServletResponse();
            assertThrows(ServiceException.class, () -> controller.export(null, null, null, null,
                    null, null, null, null, null, "trace", response));
            assertEquals(0, response.getContentAsByteArray().length);
            verifyNoInteractions(context.getBean(EbayReplenishmentV2PythonClient.class));
        }
        finally { SecurityContextHolder.clearContext(); RequestContextHolder.resetRequestAttributes(); }
    }

    @Test
    void exportUsesSessionNotClientSuppliedPermissionsOrColumns() throws Exception
    {
        login(Set.of(LIST, EXPORT, FIELD + "sku"));
        try (var context = new AnnotationConfigApplicationContext(Config.class))
        {
            var client = context.getBean(EbayReplenishmentV2PythonClient.class);
            var data = Map.of("items", List.of(Map.of("sku", "BMW-1-2", "gross_profit_amount", 123)),
                    "pagination", Map.of("total", 1));
            when(client.exportData(anyMap(), any())).thenReturn(Map.of("data", data));
            var mvc = MockMvcBuilders.standaloneSetup(context.getBean(EbayReplenishmentV2Controller.class)).build();
            var response = mvc.perform(post("/operations/ebay/replenishment-v2/export")
                    .param("permissions", "*:*:*").param("columns", "gross_profit_amount")
                    .param("calculationVersion", "0123456789abcdef0123456789abcdef"))
                    .andReturn().getResponse();
            assertEquals(200, response.getStatus());
            verify(client).exportData(argThat(params ->
                    "0123456789abcdef0123456789abcdef".equals(params.get("calculation_version"))), any());
            try (var workbook = new XSSFWorkbook(new ByteArrayInputStream(response.getContentAsByteArray())))
            {
                var sheet = workbook.getSheet("补货2.0");
                assertEquals(1, sheet.getRow(0).getLastCellNum());
                assertEquals("SKU", sheet.getRow(0).getCell(0).getStringCellValue());
                assertEquals("BMW-1-2", sheet.getRow(1).getCell(0).getStringCellValue());
                assertNull(workbook.getSheet("90天分段明细"));
            }
        }
        finally { SecurityContextHolder.clearContext(); RequestContextHolder.resetRequestAttributes(); }
    }
}
