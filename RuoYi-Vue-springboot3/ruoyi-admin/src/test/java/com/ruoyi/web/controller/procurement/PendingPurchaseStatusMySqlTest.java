package com.ruoyi.web.controller.procurement;

import com.ruoyi.system.mapper.procurement.PendingPurchaseStatusMapper;
import java.io.InputStream;
import java.math.BigDecimal;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.DriverManager;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.*;
import java.util.regex.Pattern;
import org.apache.ibatis.builder.xml.XMLMapperBuilder;
import org.apache.ibatis.datasource.unpooled.UnpooledDataSource;
import org.apache.ibatis.mapping.Environment;
import org.apache.ibatis.session.Configuration;
import org.apache.ibatis.session.SqlSessionFactoryBuilder;
import org.mybatis.spring.SqlSessionTemplate;
import org.mybatis.spring.transaction.SpringManagedTransactionFactory;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import static org.junit.jupiter.api.Assertions.*;

/** Only writes a random local fixture schema; never changes application tables. */
@EnabledIfEnvironmentVariable(named="PENDING_PO_MYSQL_TEST",matches="1")
class PendingPurchaseStatusMySqlTest
{
    @Test
    void matchingRespectsSiteSupplierAgeAndLateFailureRollsBackEntirePublication() throws Exception
    {
        String base=System.getenv("PENDING_PO_MYSQL_BASE");
        assertTrue(base.matches("jdbc:mysql://(127\\.0\\.0\\.1|localhost):[0-9]+/"));
        String schema="codex_pending_po_test_"+UUID.randomUUID().toString().replace("-", "").substring(0,12);
        assertTrue(schema.matches("codex_pending_po_test_[0-9a-f]{12}"));
        String options="?useSSL=false&allowPublicKeyRetrieval=true&characterEncoding=utf8&serverTimezone=Asia/Shanghai";
        String user=System.getenv("PENDING_PO_MYSQL_USER"),password=System.getenv("PENDING_PO_MYSQL_PASSWORD");
        try(var admin=DriverManager.getConnection(base+options,user,password);var sql=admin.createStatement())
        {
            sql.execute("CREATE DATABASE `"+schema+"` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci");
            try
            {
                sql.execute("USE `"+schema+"`");
                String migration=Files.readString(Path.of("../sql/20261029_pending_purchase_order_status.sql"));
                var creates=Pattern.compile("CREATE TABLE IF NOT EXISTS[\\s\\S]+?;").matcher(migration);
                int tables=0;
                while(creates.find()) { sql.execute(creates.group()); tables++; }
                assertEquals(2,tables);
                sql.execute("INSERT INTO procurement_pending_po_sync(id,updated_at) VALUES(1,NOW())");
                sql.execute("CREATE TABLE procurement_pending_purchase(id BIGINT PRIMARY KEY,site VARCHAR(100),sku VARCHAR(255)) COLLATE=utf8mb4_unicode_ci");
                sql.execute("INSERT INTO procurement_pending_purchase VALUES(1,'德国','FRD-70327-0076'),(2,'GB','FRD-70327-0076'),(3,'DE','FRD-70327-0457')");
                var ds=new UnpooledDataSource("com.mysql.cj.jdbc.Driver",base+schema+options,user,password);
                var config=new Configuration(new Environment("test",new SpringManagedTransactionFactory(),ds));
                String resource="mapper/procurement/PendingPurchaseStatusMapper.xml";
                try(InputStream in=getClass().getClassLoader().getResourceAsStream(resource))
                { assertNotNull(in); new XMLMapperBuilder(in,config,resource,config.getSqlFragments()).parse(); }
                var mapper=new SqlSessionTemplate(new SqlSessionFactoryBuilder().build(config)).getMapper(PendingPurchaseStatusMapper.class);
                var transaction=new TransactionTemplate(new DataSourceTransactionManager(ds));
                LocalDate today=LocalDate.now();
                List<Map<String,Object>> rows=new ArrayList<>(List.of(row("PO1","1","DE"),row("PO1","2","DE"),
                    row("PO2","3","DE"),row("PO3","4","UK"),row("PO4","5","UNKNOWN")));
                var old=row("OLD","6","DE"); old.put("sourceCreated",today.minusMonths(7).atStartOfDay()); rows.add(old);
                transaction.executeWithoutResult(tx -> { mapper.insertRows(rows); mapper.publish(today.minusMonths(6),today,rows.size()); });
                var summary=mapper.selectSummary(List.of(1L,2L,3L));
                assertEquals(3,summary.size());
                var de=summary.stream().filter(r -> ((Number)r.get("id")).longValue()==1L).findFirst().orElseThrow();
                assertEquals(2,((Number)de.get("orderCount")).intValue());
                assertEquals(1,((Number)de.get("unclassifiedCount")).intValue());
                assertEquals(4,mapper.selectDetails(1L).size());
                assertEquals(2,mapper.selectDetails(2L).size());
                assertTrue(mapper.selectDetails(3L).isEmpty());
                assertTrue(mapper.selectDetails(999L).isEmpty());
                assertThrows(RuntimeException.class,() -> transaction.executeWithoutResult(tx -> {
                    mapper.clearSnapshot();
                    mapper.insertRows(List.of(row("NEW","100","DE")));
                    mapper.publish(today,today,1);
                    mapper.insertRows(List.of(row("NEW","100","DE"))); // late duplicate PK
                }));
                assertEquals(4,mapper.selectDetails(1L).size());
                assertEquals(rows.size(),((Number)mapper.selectState().get("rowCount")).intValue());
                assertEquals("SUCCESS",mapper.selectState().get("state"));
            }
            finally { sql.execute("DROP DATABASE `"+schema+"`"); }
        }
    }

    private Map<String,Object> row(String order,String item,String site)
    {
        Map<String,Object> row=new HashMap<>();
        row.put("orderSn",order);row.put("itemId",item);row.put("site",site);row.put("sku","FRD-70327-0076");
        row.put("sourceCreated",LocalDateTime.now());row.put("rawJson","{}");
        row.put("orderStatus","待到货");row.put("arrivalStatus","部分到货");row.put("payStatus","已付款");
        row.put("quantityReal",BigDecimal.TEN);
        return row;
    }
}
