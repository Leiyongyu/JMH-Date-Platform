package com.ruoyi.system.service.operation.external.lingxing;

import com.ruoyi.system.domain.operation.external.AmzRestockSummary;
import com.ruoyi.system.mapper.operation.external.ShopListMapper;
import java.util.*;
import java.util.stream.IntStream;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.test.util.ReflectionTestUtils;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class AmzRestockSummarySyncServiceTest
{
    private LingxingGatewayService gateway;
    private AmzRestockSummaryReplaceService replacement;
    private ShopListMapper shops;
    private AmzRestockSummarySyncService service;

    @BeforeEach
    void setup()
    {
        gateway=mock(LingxingGatewayService.class); replacement=mock(AmzRestockSummaryReplaceService.class);
        shops=mock(ShopListMapper.class); service=new AmzRestockSummarySyncService(gateway,replacement,shops);
        ReflectionTestUtils.setField(service,"sidBatchSize",10);
        when(shops.selectSidsByPlatform("10001",1)).thenReturn(List.of("1"));
        when(replacement.replaceAll(anyList())).thenAnswer(i -> ((List<?>)i.getArgument(0)).size());
    }

    static Map<String,Object> item(String hash,int sid,int node,int sales,Map<String,Object>... children)
    {
        return new LinkedHashMap<>(Map.of("basic_info",new LinkedHashMap<>(Map.of("hash_id",hash,"sid",sid,"node_type",node,
                "msku_fnsku_list",List.of(Map.of("msku","MSKU")))),
                "sales_info",new LinkedHashMap<>(Map.of("sales_total_30",sales)),"item_list",List.of(children)));
    }

    static Map<String,Object> page(int total,Map<String,Object>... rows)
    { return Map.of("code",0,"total",total,"data",List.of(rows)); }

    @Test
    void defaultQueriesAllShopsOnceAndTraversesFiftyRowPages() throws Exception
    {
        service=new AmzRestockSummarySyncService(gateway,replacement,shops);
        var allSids=IntStream.rangeClosed(1,133).mapToObj(Integer::toString).toList();
        when(shops.selectSidsByPlatform("10001",1)).thenReturn(allSids);
        var first=IntStream.range(0,50).mapToObj(i -> item("row-"+i,1,3,i)).toList();
        when(gateway.post(anyString(),anyMap())).thenReturn(
                Map.of("code",0,"total",51,"data",first),page(51,item("last",133,3,8)));
        service.syncAll();
        ArgumentCaptor<Map<String,Object>> requests=ArgumentCaptor.forClass(Map.class);
        verify(gateway,times(2)).post(anyString(),requests.capture());
        for (var request:requests.getAllValues())
        {
            assertEquals(allSids,request.get("sid_list"));
            assertEquals(50,request.get("length"));
        }
        assertEquals(50,requests.getAllValues().get(1).get("offset"));
        verify(replacement).replaceAll(argThat(rows -> rows.size()==51));
    }

    @Test
    void changingTotalRestartsAtZeroAndDiscardsAbandonedRows() throws Exception
    {
        when(gateway.post(anyString(),anyMap())).thenReturn(
                page(2,item("abandoned",1,3,99)), page(3,item("discarded",1,3,98)),
                page(1,item("stable",1,3,7)));
        service.syncAll();
        verify(replacement).replaceAll(argThat(rows -> rows.size()==1 && rows.get(0).getHashId().equals("stable")));
        ArgumentCaptor<Map<String,Object>> requests=ArgumentCaptor.forClass(Map.class);
        verify(gateway,times(3)).post(anyString(),requests.capture());
        assertEquals(List.of(0,1,0),requests.getAllValues().stream().map(r -> r.get("offset")).toList());
    }

    @Test
    void missingTotalCanRecoverButPersistentMissingTotalNeverPublishes() throws Exception
    {
        Map<String,Object> missing=Map.of("code",0,"data",List.of());
        when(gateway.post(anyString(),anyMap())).thenReturn(missing,page(1,item("ok",1,3,3)));
        service.syncAll();
        verify(replacement).replaceAll(argThat(rows -> rows.size()==1));
        reset(gateway,replacement);
        when(gateway.post(anyString(),anyMap())).thenReturn(missing);
        var failure=assertThrows(IllegalStateException.class,service::syncAll);
        assertTrue(failure.getMessage().contains("offset=0"));
        verify(gateway,times(3)).post(anyString(),anyMap());
        verifyNoInteractions(replacement);
    }

    @Test
    void allShopBatchesAndCountryChildrenAreCollectedBeforePublishing() throws Exception
    {
        when(shops.selectSidsByPlatform("10001",1)).thenReturn(IntStream.rangeClosed(1,13).mapToObj(Integer::toString).toList());
        var europe=item("eu",1,1,51,item("de",1,2,14),item("fr",2,2,18),item("es",3,2,8),
                item("it",4,2,6),item("be",5,2,4),item("nl",6,2,1));
        var other=item("cq",11,1,13,item("cq-de",11,2,7),item("cq-fr",12,2,4),item("cq-nl",13,2,2));
        when(gateway.post(anyString(),anyMap())).thenReturn(page(2,europe,item("uk",7,3,7)),page(1,other));
        service.syncAll();
        ArgumentCaptor<List<AmzRestockSummary>> captured=ArgumentCaptor.forClass(List.class);
        var order=inOrder(gateway,replacement);
        order.verify(gateway,times(2)).post(anyString(),anyMap());
        order.verify(replacement).replaceAll(captured.capture());
        var rows=captured.getValue();
        assertEquals(12,rows.size());
        assertEquals(71,rows.stream().filter(r -> r.getNodeType()!=1).mapToInt(AmzRestockSummary::getSales30d).sum());
        assertEquals(21,rows.stream().filter(r -> r.getNodeType()==2 && Set.of(1,11).contains(r.getSid())).mapToInt(AmzRestockSummary::getSales30d).sum());
        ArgumentCaptor<Map<String,Object>> requests=ArgumentCaptor.forClass(Map.class);
        verify(gateway,times(2)).post(anyString(),requests.capture());
        assertEquals(50,requests.getAllValues().get(0).get("length"));
        assertEquals(List.of("11","12","13"),requests.getAllValues().get(1).get("sid_list"));
    }

    @Test
    void aShortPageDoesNotEndBeforeTheReportedTotalAndOffsetsUseActualRows() throws Exception
    {
        when(gateway.post(anyString(),anyMap())).thenReturn(page(3,item("a",1,3,1),item("b",1,3,2)),page(3,item("c",1,3,3)));
        service.syncAll();
        ArgumentCaptor<Map<String,Object>> requests=ArgumentCaptor.forClass(Map.class);
        verify(gateway,times(2)).post(anyString(),requests.capture());
        assertEquals(2,requests.getAllValues().get(1).get("offset"));
        verify(replacement).replaceAll(argThat(rows -> rows.size()==3));
    }

    @Test
    void failureInTheLastShopBatchDoesNotPublishTheFirstBatch() throws Exception
    {
        when(shops.selectSidsByPlatform("10001",1)).thenReturn(IntStream.rangeClosed(1,11).mapToObj(Integer::toString).toList());
        when(gateway.post(anyString(),anyMap())).thenReturn(page(1,item("a",1,3,1))).thenThrow(new IllegalStateException("upstream failed"));
        assertThrows(IllegalStateException.class,service::syncAll);
        verifyNoInteractions(replacement);
    }

    @Test
    void missingPageChangingTotalsAndRepeatedPagesNeverPublish() throws Exception
    {
        when(gateway.post(anyString(),anyMap())).thenReturn(page(2,item("a",1,3,1)),page(2));
        assertThrows(IllegalStateException.class,service::syncAll);
        reset(gateway);
        when(gateway.post(anyString(),anyMap())).thenReturn(page(2,item("a",1,3,1)),page(3,item("b",1,3,2)));
        assertThrows(IllegalStateException.class,service::syncAll);
        reset(gateway);
        when(gateway.post(anyString(),anyMap())).thenReturn(page(2,item("a",1,3,1)),page(2,item("a",1,3,1)));
        assertThrows(IllegalStateException.class,service::syncAll);
        verifyNoInteractions(replacement);
    }

    @Test
    void invalidResponsesAndAnEmptyGlobalResultKeepPreviousData() throws Exception
    {
        for (var response:List.of(Map.of("code",500,"total",0,"data",List.of()),
                Map.of("code",0,"data",List.of()),page(0),Map.of("code",0,"total",1,"data",List.of(Map.of()))))
        {
            when(gateway.post(anyString(),anyMap())).thenReturn((Map)response);
            assertThrows(IllegalStateException.class,service::syncAll);
        }
        verifyNoInteractions(replacement);
    }

    @Test
    void zeroAndAbsentSalesStayDistinctAndCountryAliasesCannotMultiplySales() throws Exception
    {
        var missing=item("missing",1,3,0); missing.remove("sales_info");
        when(gateway.post(anyString(),anyMap())).thenReturn(page(2,item("zero",1,3,0),missing));
        service.syncAll();
        verify(replacement).replaceAll(argThat(rows -> rows.get(0).getSales30d()==0 && rows.get(1).getSales30d()==null));
        reset(replacement);
        var aliases=item("aliases",1,2,10);
        ((Map)aliases.get("basic_info")).put("msku_fnsku_list",List.of(Map.of("msku","A"),Map.of("msku","B")));
        when(gateway.post(anyString(),anyMap())).thenReturn(page(1,aliases));
        assertThrows(IllegalStateException.class,service::syncAll);
        verifyNoInteractions(replacement);
    }

    @Test
    void duplicateSharedRowsAcrossBatchesAreNotCountedTwice() throws Exception
    {
        when(shops.selectSidsByPlatform("10001",1)).thenReturn(IntStream.rangeClosed(1,11).mapToObj(Integer::toString).toList());
        when(gateway.post(anyString(),anyMap())).thenReturn(page(1,item("same",1,2,8)));
        service.syncAll();
        verify(replacement).replaceAll(argThat(rows -> rows.size()==1 && rows.get(0).getSales30d()==8));
    }

    @Test
    void cancellationAfterReceivingAResponseDoesNotPublish() throws Exception
    {
        when(gateway.post(anyString(),anyMap())).thenAnswer(i -> { Thread.currentThread().interrupt(); return page(1,item("a",1,3,1)); });
        try { assertThrows(IllegalStateException.class,service::syncAll); }
        finally { Thread.interrupted(); }
        verifyNoInteractions(replacement);
    }

    @Test
    void missingCountrySalesCannotSilentlyPublishANonzeroSharedParent() throws Exception
    {
        when(gateway.post(anyString(),anyMap())).thenReturn(page(1,item("parent",1,1,51,item("de-only",1,2,14))));
        assertThrows(IllegalStateException.class,service::syncAll);
        verifyNoInteractions(replacement);
    }
}
