package com.ruoyi.web.controller.operation;

import com.ruoyi.system.domain.operation.AmzMixedSalesQuery;
import com.ruoyi.system.mapper.operation.AmzMixedSalesMapper;
import java.io.InputStream;
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.Statement;
import java.util.Map;
import java.util.UUID;
import org.apache.ibatis.builder.xml.XMLMapperBuilder;
import org.apache.ibatis.datasource.unpooled.UnpooledDataSource;
import org.apache.ibatis.mapping.Environment;
import org.apache.ibatis.session.Configuration;
import org.apache.ibatis.session.SqlSessionFactoryBuilder;
import org.apache.ibatis.transaction.jdbc.JdbcTransactionFactory;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import static org.junit.jupiter.api.Assertions.*;

/** Only a newly-created local fixture schema is mutated or dropped. */
@EnabledIfEnvironmentVariable(named = "MIXED_SALES_MYSQL_TEST", matches = "1")
class AmzMixedSalesMySqlTest
{
    @Test
    void existingLocalSourcesAreReadOnlyAndDetailSumsMatchParent() throws Exception
    {
        String base = System.getenv("MIXED_SALES_MYSQL_BASE");
        assertTrue(base.matches("jdbc:mysql://(127\\.0\\.0\\.1|localhost):[0-9]+/"));
        String options = "?useSSL=false&allowPublicKeyRetrieval=true&characterEncoding=utf8&serverTimezone=Asia/Shanghai";
        var factory = new SqlSessionFactoryBuilder().build(configuration(base + "jmh_data_platform" + options));
        try (var session = factory.openSession())
        {
            session.getConnection().setReadOnly(true);
            var mapper = session.getMapper(AmzMixedSalesMapper.class);
            var q = new AmzMixedSalesQuery(); q.setPageSize(5);
            q.setSortField("fbaTotalInventory"); q.setSortOrder("desc");
            long began = System.nanoTime();
            long total = mapper.countProducts(q);
            var rows = mapper.selectProducts(q);
            try (var statement = session.getConnection().createStatement();
                 var count = statement.executeQuery("SELECT COUNT(DISTINCT UPPER(TRIM(sku))) FROM amz_warehouse_inventory_detail WHERE sku IS NOT NULL AND TRIM(sku)!=''"))
            {
                assertTrue(count.next()); assertEquals(count.getLong(1), total);
            }
            for (var row : rows)
            {
                q.setSku((String) row.get("sku")); q.setPageSize(200);
                var details = mapper.selectDetails(q);
                assertEquals(((Number) row.get("listingCount")).longValue(), mapper.countDetails(q));
                if (details.size() < 200)
                    for (String field : new String[]{"fbaStock", "fbaInbound", "fbaTotalInventory", "sales30d"})
                    {
                        BigDecimal sum = null;
                        for (var detail : details)
                            if (detail.get(field) != null)
                                sum = (sum == null ? BigDecimal.ZERO : sum).add(new BigDecimal(detail.get(field).toString()));
                        if (sum == null) assertNull(row.get(field));
                        else assertEquals(0, sum.compareTo(new BigDecimal(row.get(field).toString())));
                    }
            }
            System.out.println("Mixed sales local read-only: products=" + total + ", checked=" + rows.size()
                    + ", elapsedMs=" + (System.nanoTime()-began)/1_000_000);
        }
    }

    private Configuration configuration(String url) throws Exception
    {
        var dataSource = new UnpooledDataSource("com.mysql.cj.jdbc.Driver", url,
                System.getenv("MIXED_SALES_MYSQL_USER"), System.getenv("MIXED_SALES_MYSQL_PASSWORD"));
        var config = new Configuration(new Environment("test", new JdbcTransactionFactory(), dataSource));
        String resource = "mapper/operation/AmzMixedSalesMapper.xml";
        try (InputStream in = getClass().getClassLoader().getResourceAsStream(resource))
        {
            assertNotNull(in);
            new XMLMapperBuilder(in, config, resource, config.getSqlFragments()).parse();
        }
        return config;
    }

    @Test
    void warehousesAndRestockNodesDoNotMultiplyStockAndMissingValuesRemainNull() throws Exception
    {
        String base = System.getenv("MIXED_SALES_MYSQL_BASE");
        assertTrue(base.matches("jdbc:mysql://(127\\.0\\.0\\.1|localhost):[0-9]+/"));
        String schema = "codex_mixed_test_" + UUID.randomUUID().toString().replace("-", "").substring(0, 12);
        assertTrue(schema.matches("codex_mixed_test_[0-9a-f]{12}"));
        String options = "?useSSL=false&allowPublicKeyRetrieval=true&characterEncoding=utf8&serverTimezone=Asia/Shanghai";
        try (Connection admin = DriverManager.getConnection(base + options,
                System.getenv("MIXED_SALES_MYSQL_USER"), System.getenv("MIXED_SALES_MYSQL_PASSWORD"));
             Statement sql = admin.createStatement())
        {
            sql.execute("CREATE DATABASE `" + schema + "` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci");
            try
            {
                sql.execute("USE `" + schema + "`");
                sql.execute("CREATE TABLE warehouse(wid INT,name VARCHAR(100))");
                sql.execute("CREATE TABLE amz_warehouse_inventory_detail(wid INT,sku VARCHAR(100),sync_time DATETIME)");
                sql.execute("CREATE TABLE amz_product_listing(sid INT,seller_sku VARCHAR(100),local_sku VARCHAR(100),local_name VARCHAR(100),small_image_url VARCHAR(100),asin VARCHAR(30),marketplace VARCHAR(30),principal_name VARCHAR(100),sync_time DATETIME,price DECIMAL(10,2),currency_code VARCHAR(16),UNIQUE KEY(sid,seller_sku))");
                sql.execute("CREATE TABLE amz_product_performance_inventory(sid INT,seller_sku VARCHAR(100),local_sku VARCHAR(100),fba_stock INT,fba_inbound INT,sync_time DATETIME,UNIQUE KEY(sid,seller_sku))");
                sql.execute("CREATE TABLE amz_restock_summary(sid INT,msku VARCHAR(100),sales_30d INT,node_type INT,updated_at DATETIME)");
                sql.execute("CREATE TABLE shop_list(sid INT,store_name VARCHAR(100),platform_code VARCHAR(30),currency VARCHAR(16))");
                sql.execute("INSERT INTO warehouse VALUES(1,'成都仓'),(2,'美国仓')");
                sql.execute("INSERT INTO amz_warehouse_inventory_detail VALUES(1,'SKU-A',NOW()),(2,'SKU-A',NOW()),(1,'SKU-B',NOW()),(2,'SKU-NO-LIST',NOW())");
                sql.execute("INSERT INTO amz_product_listing(sid,seller_sku,local_sku,local_name,small_image_url,asin,marketplace,principal_name,sync_time) VALUES(1,'A1','SKU-A','产品A','img','ASINA','美国','负责人',NOW()),(2,'A2','SKU-A','产品A','img','ASINA','德国','负责人',NOW()),(1,'B','SKU-B','产品B','img','ASINB','美国','负责人',NOW()),(1,'OUT','OUTSIDE','不在仓库','img','ASIN','美国','负责人',NOW())");
                sql.execute("UPDATE amz_product_listing SET price=12.34,currency_code='GBP' WHERE sid=1");
                sql.execute("INSERT INTO amz_product_performance_inventory VALUES(1,'A1','SKU-A',10,2,NOW()),(2,'A2','SKU-A',7,1,NOW()),(3,'A3','SKU-A',4,0,NOW())");
                sql.execute("INSERT INTO amz_restock_summary VALUES(1,'A1',999,1,'2026-10-27'),(1,'A1',5,2,'2026-10-27'),(1,'A1',3,2,'2026-10-27'),(2,'A2',6,3,'2026-10-27'),(1,'B',0,3,'2026-10-27')");
                sql.execute("INSERT INTO shop_list VALUES(1,'店铺一','10001','USD'),(1,'店铺一','10001','USD'),(2,'店铺二','10001','EUR')");
                var factory = new SqlSessionFactoryBuilder().build(configuration(base + schema + options));
                try (var session = factory.openSession())
                {
                    var mapper = session.getMapper(AmzMixedSalesMapper.class);
                    var q = new AmzMixedSalesQuery(); q.setSortField("fbaTotalInventory"); q.setSortOrder("desc");
                    assertEquals(3, mapper.countProducts(q));
                    var rows = mapper.selectProducts(q);
                    var a = rows.get(0);
                    assertEquals("SKU-A", a.get("sku"));
                    assertEquals(new BigDecimal("24"), a.get("fbaTotalInventory"));
                    assertEquals(new BigDecimal("11"), a.get("sales30d"));
                    assertEquals(3L, a.get("listingCount"));
                    assertEquals(3L, a.get("storeCount"));
                    assertEquals(2L, a.get("salesMatchedCount"));
                    var b = rows.stream().filter(r -> "SKU-B".equals(r.get("sku"))).findFirst().orElseThrow();
                    assertNull(b.get("fbaTotalInventory"));
                    assertEquals(BigDecimal.ZERO, b.get("sales30d"));
                    q.setSku("SKU-A");
                    assertEquals(3, mapper.countDetails(q));
                    assertEquals(3, mapper.selectDetails(q).size());
                    assertEquals(new BigDecimal("12.34"),mapper.selectDetails(q).get(0).get("salePrice"));
                    assertEquals("GBP",mapper.selectDetails(q).get(0).get("currency"));
                    q.setSid(1);
                    assertEquals(new BigDecimal("12"), mapper.selectProducts(q).get(0).get("fbaTotalInventory"));
                    assertEquals(1, mapper.countDetails(q));
                    q.setSid(null); q.setSku("X' OR 1=1 --");
                    assertEquals(0, mapper.countProducts(q));
                    q.setSku(null); q.setPageSize(1); q.setPageNum(2);
                    assertEquals(1, mapper.selectProducts(q).size());
                    for (String field : new String[]{"sku","fbaStock","fbaInbound","fbaTotalInventory","sales30d"})
                    {
                        q.setSortField(field); q.setSortOrder("asc");
                        assertEquals(1, mapper.selectProducts(q).size());
                    }
                    assertEquals(2, mapper.selectStores().size());
                }
            }
            finally
            {
                sql.execute("DROP DATABASE `" + schema + "`");
            }
        }
    }
}
