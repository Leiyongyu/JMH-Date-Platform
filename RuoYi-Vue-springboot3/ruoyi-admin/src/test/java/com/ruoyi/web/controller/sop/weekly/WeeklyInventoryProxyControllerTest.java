package com.ruoyi.web.controller.sop.weekly;

import com.ruoyi.system.service.finance.PythonPerformanceTaskProperties;
import com.ruoyi.web.controller.sop.image.ImageSopSessionService;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class WeeklyInventoryProxyControllerTest
{
    @Test void rejectsMissingAndForgedSessionsBeforeForwarding() throws Exception
    {
        ImageSopSessionService sessions=mock(ImageSopSessionService.class);
        WeeklyInventoryProxyController controller=new WeeklyInventoryProxyController(sessions,new PythonPerformanceTaskProperties());
        for(String token : new String[]{null,"forged"})
        {
            MockHttpServletRequest request=new MockHttpServletRequest("POST","/sop/weekly-inventory/proxy/run");
            if(token!=null)request.setQueryString("erp_session="+token);
            MockHttpServletResponse response=new MockHttpServletResponse();
            controller.proxy(request,response);
            assertEquals(403,response.getStatus());
            verify(sessions).validateAndTouch(token,"sop:weeklyInventory:use");
        }
    }
    @Test void strictMethodAndPathWhitelist()
    {
        assertTrue(WeeklyInventoryProxyController.allowed("GET","/files/1/download"));
        assertTrue(WeeklyInventoryProxyController.allowed("POST","/run"));
        assertFalse(WeeklyInventoryProxyController.allowed("GET","/run"));
        assertFalse(WeeklyInventoryProxyController.allowed("POST","/files"));
        assertFalse(WeeklyInventoryProxyController.allowed("GET","/files/../secret"));
        assertFalse(WeeklyInventoryProxyController.allowed("GET","/files/%2e%2e/download"));
    }
    @Test void onlyQueryStringIsParsed()
    {
        assertEquals("abc+123",WeeklyInventoryProxyController.query("api_base=x&erp_session=abc%2B123","erp_session"));
        assertThrows(IllegalArgumentException.class,()->WeeklyInventoryProxyController.query("erp_session=a&erp_session=b","erp_session"));
    }
}
