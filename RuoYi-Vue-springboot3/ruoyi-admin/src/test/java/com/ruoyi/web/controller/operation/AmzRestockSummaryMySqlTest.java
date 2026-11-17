package com.ruoyi.web.controller.operation;

import com.ruoyi.system.domain.operation.external.AmzRestockSummary;
import com.ruoyi.system.mapper.operation.external.AmzRestockSummaryMapper;
import com.ruoyi.system.mapper.operation.external.ShopListMapper;
import com.ruoyi.system.mapper.operation.AmzMixedSalesMapper;
import com.ruoyi.system.domain.operation.AmzMixedSalesQuery;
import com.ruoyi.system.service.operation.external.lingxing.AmzRestockSummaryReplaceService;
import com.ruoyi.system.service.operation.external.lingxing.AmzRestockSummarySyncService;
import com.ruoyi.system.service.operation.external.lingxing.LingxingGatewayService;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.InputStream;
import java.sql.DriverManager;
import java.util.*;
import java.nio.file.Files;
import java.nio.file.Path;
import java.math.BigDecimal;
import org.apache.ibatis.builder.xml.XMLMapperBuilder;
import org.apache.ibatis.datasource.unpooled.UnpooledDataSource;
import org.apache.ibatis.mapping.Environment;
import org.apache.ibatis.session.Configuration;
import org.apache.ibatis.session.SqlSessionFactoryBuilder;
import org.mybatis.spring.SqlSessionTemplate;
import org.mybatis.spring.transaction.SpringManagedTransactionFactory;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.aop.framework.ProxyFactory;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.annotation.AnnotationTransactionAttributeSource;
import org.springframework.transaction.interceptor.TransactionInterceptor;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

/** No business writes: only a newly-created, random local fixture schema is changed. */
@EnabledIfEnvironmentVariable(named="MIXED_SALES_MYSQL_TEST",matches="1")
class AmzRestockSummaryMySqlTest
{
    @Test
    void lateInsertFailureRollsBackDeleteAndEveryEarlierInsertBatch() throws Exception
    {
        String base=System.getenv("MIXED_SALES_MYSQL_BASE");
        assertTrue(base.matches("jdbc:mysql://(127\\.0\\.0\\.1|localhost):[0-9]+/"));
        String schema="codex_restock_test_"+UUID.randomUUID().toString().replace("-","").substring(0,12);
        assertTrue(schema.matches("codex_restock_test_[0-9a-f]{12}"));
        String options="?useSSL=false&allowPublicKeyRetrieval=true&characterEncoding=utf8&serverTimezone=Asia/Shanghai";
        String user=System.getenv("MIXED_SALES_MYSQL_USER"),password=System.getenv("MIXED_SALES_MYSQL_PASSWORD");
        try(var admin=DriverManager.getConnection(base+options,user,password);var sql=admin.createStatement())
        {
            sql.execute("CREATE DATABASE `"+schema+"` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci");
            try
            {
                sql.execute("CREATE TABLE `"+schema+"`.amz_restock_summary LIKE jmh_data_platform.amz_restock_summary");
                var ds=new UnpooledDataSource("com.mysql.cj.jdbc.Driver",base+schema+options,user,password);
                var config=new Configuration(new Environment("test",new SpringManagedTransactionFactory(),ds));
                String resource="mapper/operation/external/AmzRestockSummaryMapper.xml";
                try(InputStream in=getClass().getClassLoader().getResourceAsStream(resource))
                { assertNotNull(in); new XMLMapperBuilder(in,config,resource,config.getSqlFragments()).parse(); }
                var template=new SqlSessionTemplate(new SqlSessionFactoryBuilder().build(config));
                var mapper=template.getMapper(AmzRestockSummaryMapper.class);
                var proxy=new ProxyFactory(new AmzRestockSummaryReplaceService(mapper));
                proxy.setProxyTargetClass(true);
                proxy.addAdvice(new TransactionInterceptor(new DataSourceTransactionManager(ds),new AnnotationTransactionAttributeSource()));
                var service=(AmzRestockSummaryReplaceService)proxy.getProxy();
                assertEquals(2,service.replaceAll(List.of(row("old-parent",1,51),row("old-child",2,14))));
                List<AmzRestockSummary> bad=new ArrayList<>();
                for(int i=0;i<500;i++) bad.add(row("new-"+i,2,i));
                bad.add(row("new-0",2,999)); // duplicate unique key only in the second INSERT batch
                assertThrows(RuntimeException.class,()->service.replaceAll(bad));
                assertEquals(51,mapper.selectByHashId("old-parent").get(0).getSales30d());
                assertEquals(14,mapper.selectByHashId("old-child").get(0).getSales30d());
                assertTrue(mapper.selectByHashId("new-1").isEmpty());
                assertThrows(IllegalArgumentException.class,()->service.replaceAll(List.of()));
                try(var count=sql.executeQuery("SELECT COUNT(*) FROM `"+schema+"`.amz_restock_summary"))
                { assertTrue(count.next()); assertEquals(2,count.getInt(1)); }
                replayIfProvided(sql,schema,config,template,service);
            }
            finally { sql.execute("DROP DATABASE `"+schema+"`"); }
        }
    }

    private void replayIfProvided(java.sql.Statement sql,String schema,Configuration config,
            SqlSessionTemplate template,AmzRestockSummaryReplaceService replacement) throws Exception
    {
        String capture=System.getenv("AMZ_RESTOCK_REPLAY_FILE");
        if(capture==null || capture.isBlank()) return;
        var lines=Files.readAllLines(Path.of(capture));
        Map<String,Object> saved=new ObjectMapper().readValue(lines.get(lines.size()-1),Map.class);
        List<Map<String,Object>> data=new ArrayList<>();
        for(var row:(List<Map<String,Object>>)saved.get("matches")) data.add(upstream(row));
        var gateway=mock(LingxingGatewayService.class);
        var shops=mock(ShopListMapper.class);
        when(shops.selectSidsByPlatform("10001",1)).thenReturn(List.of("12531","12533","12590","12592","12606","12608","12616"));
        when(gateway.post(anyString(),anyMap())).thenReturn(Map.of("code",0,"total",data.size(),"data",data));
        new AmzRestockSummarySyncService(gateway,replacement,shops).syncAll();
        for(String table:List.of("warehouse","shop_list","amz_warehouse_inventory_detail","amz_product_listing","amz_product_performance_inventory"))
        {
            sql.execute("CREATE TABLE `"+schema+"`."+table+" LIKE jmh_data_platform."+table);
            String filter=Set.of("warehouse","shop_list").contains(table)?"":
                    " WHERE "+(table.equals("amz_warehouse_inventory_detail")?"sku":"local_sku")+"='PSA-60008-0128'";
            sql.execute("INSERT INTO `"+schema+"`."+table+" SELECT * FROM jmh_data_platform."+table+filter);
        }
        String resource="mapper/operation/AmzMixedSalesMapper.xml";
        try(InputStream in=getClass().getClassLoader().getResourceAsStream(resource))
        { assertNotNull(in); new XMLMapperBuilder(in,config,resource,config.getSqlFragments()).parse(); }
        var mixed=template.getMapper(AmzMixedSalesMapper.class);
        var query=new AmzMixedSalesQuery(); query.setSku("PSA-60008-0128"); query.setPageSize(200);
        query.setSortField("sku"); query.setSortOrder("asc");
        var parent=mixed.selectProducts(query).get(0);
        assertEquals(0,new BigDecimal("71").compareTo(new BigDecimal(parent.get("sales30d").toString())));
        Map<Integer,String> countries=new HashMap<>();
        try(var rs=sql.executeQuery("SELECT sid,MAX(country_code) country FROM `"+schema+"`.shop_list WHERE platform_code='10001' GROUP BY sid"))
        { while(rs.next()) countries.put(rs.getInt("sid"),rs.getString("country")); }
        Map<String,Integer> actual=new HashMap<>();
        for(var row:mixed.selectDetails(query))
            if(row.get("sales30d")!=null)
                actual.merge(countries.get(((Number)row.get("sid")).intValue()),((Number)row.get("sales30d")).intValue(),Integer::sum);
        assertEquals(Map.of("DE",21,"FR",22,"ES",8,"IT",6,"BE",4,"NL",3,"UK",7),actual);
        System.out.println("Captured API replay verified: SKU PSA-60008-0128 total 71; site sales "+actual);
    }

    private static Map<String,Object> upstream(Map<String,Object> saved)
    {
        Map<String,Object> row=new LinkedHashMap<>();
        row.put("basic_info",saved.get("basic")); row.put("sales_info",saved.get("sales"));
        row.put("amazon_quantity_info",saved.get("inventory"));
        List<Map<String,Object>> children=new ArrayList<>();
        for(var child:(List<Map<String,Object>>)saved.get("children")) children.add(upstream(child));
        row.put("item_list",children);
        return row;
    }

    private static AmzRestockSummary row(String hash,int type,int sales)
    {
        var row=new AmzRestockSummary();
        row.setHashId(hash); row.setSid(1); row.setMsku("MSKU"); row.setNodeType(type); row.setSales30d(sales);
        return row;
    }
}
