package com.ruoyi.system.service.operation;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.system.service.finance.PerformancePythonProperties;
import com.ruoyi.system.service.operation.ebay.EbayReplenishmentV2PythonClient;
import com.ruoyi.system.service.operation.scope.BusinessDataScope;
import com.ruoyi.system.service.operation.scope.BusinessDataScopeService;
import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.test.util.ReflectionTestUtils;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class EbayReplenishmentDataScopeTest
{
    @Test void serverOverwritesForgedScopeAndDeniesOutOfScopeWrites() throws Exception
    {
        List<String> requests=Collections.synchronizedList(new ArrayList<>());
        var server=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0);
        server.createContext("/",exchange -> {
            requests.add(exchange.getRequestMethod()+" "+URLDecoder.decode(exchange.getRequestURI().toString(),StandardCharsets.UTF_8));
            byte[] body="{\"code\":0,\"data\":{\"items\":[]}}".getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(200,body.length);
            exchange.getResponseBody().write(body);exchange.close();
        });
        server.start();
        try {
            var properties=new PerformancePythonProperties();
            properties.setBaseUrl("http://127.0.0.1:"+server.getAddress().getPort());
            var client=new EbayReplenishmentV2PythonClient(properties,new ObjectMapper());
            var scope=mock(BusinessDataScopeService.class);
            ReflectionTestUtils.setField(client,"dataScope",scope);
            when(scope.resolve(BusinessDataScopeService.EBAY)).thenReturn(new BusinessDataScope(false,List.of("甲")));
            var forged=Map.of("allowed_principals","null","principal_name","乙");
            client.list(forged,null);client.hierarchy(forged,null);client.exportData(forged,null);
            for(String request:requests) {
                assertTrue(request.contains("allowed_principals=[\"甲\"]"),request);
                assertTrue(request.contains("principal_name=乙"),request);
            }
            var body=Map.of("site","德国","sku","OTHER");
            assertThrows(AccessDeniedException.class,()->client.saveReviewNote(body,null));
            assertThrows(AccessDeniedException.class,()->client.confirmReview(body,null));
            assertThrows(AccessDeniedException.class,()->client.saveSalesType(body,null));
            assertThrows(AccessDeniedException.class,()->client.forecastRuleSku(body,null));
            assertTrue(requests.stream().allMatch(r->r.startsWith("GET ")));
            when(scope.resolve(BusinessDataScopeService.EBAY)).thenReturn(new BusinessDataScope(true,List.of()));
            client.exportData(forged,null);
            assertTrue(requests.get(requests.size()-1).contains("allowed_principals=null"));
        } finally {server.stop(0);}
    }
}
