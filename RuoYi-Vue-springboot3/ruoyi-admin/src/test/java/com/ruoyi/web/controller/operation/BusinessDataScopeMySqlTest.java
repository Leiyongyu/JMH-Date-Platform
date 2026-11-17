package com.ruoyi.web.controller.operation;

import com.ruoyi.system.mapper.operation.BusinessDataScopeMapper;
import com.ruoyi.system.mapper.operation.AmzReplenishmentSnapshotMapper;
import com.ruoyi.system.service.operation.scope.BusinessDataScope;
import com.ruoyi.system.service.operation.scope.BusinessDataScopeService;
import com.ruoyi.system.domain.operation.AmzReplenishmentSnapshot;
import java.sql.DriverManager;
import java.util.*;
import org.apache.ibatis.builder.xml.XMLMapperBuilder;
import org.apache.ibatis.datasource.unpooled.UnpooledDataSource;
import org.apache.ibatis.mapping.Environment;
import org.apache.ibatis.session.Configuration;
import org.apache.ibatis.session.SqlSessionFactoryBuilder;
import org.apache.ibatis.transaction.jdbc.JdbcTransactionFactory;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import static org.junit.jupiter.api.Assertions.*;

/** Creates only a disposable local schema; business tables are never modified. */
@EnabledIfEnvironmentVariable(named="MIXED_SALES_MYSQL_TEST", matches="1")
class BusinessDataScopeMySqlTest
{
    @Test void liveAuthorizationAndAllAmzReadPathsEnforceTheSameScope() throws Exception
    {
        String base=System.getenv("MIXED_SALES_MYSQL_BASE");
        assertTrue(base.matches("jdbc:mysql://(127\\.0\\.0\\.1|localhost):[0-9]+/"));
        String schema="codex_scope_test_"+UUID.randomUUID().toString().replace("-", "").substring(0,12);
        assertTrue(schema.matches("codex_scope_test_[0-9a-f]{12}"));
        String options="?useSSL=false&allowPublicKeyRetrieval=true&characterEncoding=utf8&serverTimezone=Asia/Shanghai";
        String user=System.getenv("MIXED_SALES_MYSQL_USER"), password=System.getenv("MIXED_SALES_MYSQL_PASSWORD");
        try (var connection=DriverManager.getConnection(base+options,user,password); var sql=connection.createStatement())
        {
            sql.execute("CREATE DATABASE `"+schema+"` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci");
            try
            {
                sql.execute("USE `"+schema+"`");
                sql.execute("CREATE TABLE sys_user(user_id BIGINT,dept_id BIGINT,nick_name VARCHAR(100),status CHAR(1),del_flag CHAR(1))");
                sql.execute("CREATE TABLE sys_role(role_id BIGINT,status CHAR(1),del_flag CHAR(1))");
                sql.execute("CREATE TABLE sys_user_role(user_id BIGINT,role_id BIGINT)");
                sql.execute("CREATE TABLE sys_role_menu(role_id BIGINT,menu_id BIGINT)");
                sql.execute("CREATE TABLE sys_menu(menu_id BIGINT,status CHAR(1),perms VARCHAR(100))");
                sql.execute("CREATE TABLE sys_business_owner_binding(owner_name VARCHAR(100) COLLATE utf8mb4_0900_bin PRIMARY KEY,user_id BIGINT)");
                sql.execute("INSERT INTO sys_user VALUES(2,10,'甲','0','0'),(3,10,'乙','0','0'),(4,11,'丙','0','0'),(5,10,'停用','1','0')");
                sql.execute("INSERT INTO sys_business_owner_binding VALUES('甲',2),('乙',3),('丙',4),('停用',5)");
                sql.execute("INSERT INTO sys_role VALUES(20,'0','0'),(21,'0','0'),(22,'1','0')");
                sql.execute("INSERT INTO sys_user_role VALUES(2,20),(2,22)");
                sql.execute("INSERT INTO sys_menu VALUES(100,'0','operations:amzReplenishment:data:self'),(101,'0','operations:amzReplenishment:data:dept'),(102,'0','operations:amzReplenishment:data:all')");
                sql.execute("INSERT INTO sys_role_menu VALUES(20,100),(21,101),(22,102)");
                for (String table:List.of("amz_replenishment_us_snapshot","amz_replenishment_eu_snapshot","amz_replenishment_override","shop_list"))
                    sql.execute("CREATE TABLE `"+table+"` LIKE jmh_data_platform.`"+table+"`");
                for (int i=1;i<=4;i++)
                {
                    String owner=List.of("甲","乙","丙","未分配").get(i-1);
                    sql.execute("INSERT INTO amz_replenishment_eu_snapshot(sid,seller_sku,warehouse_sku,warehouse_name,store_name,principal_name,region_group,current_flag,sales_30d) VALUES("+i+",'SKU-"+i+"','WAREHOUSE','仓库','店铺"+i+"','"+owner+"','EU',1,"+(i*10)+")");
                }
                var config=new Configuration(new Environment("test",new JdbcTransactionFactory(),new UnpooledDataSource("com.mysql.cj.jdbc.Driver",base+schema+options,user,password)));
                config.setLocalCacheScope(org.apache.ibatis.session.LocalCacheScope.STATEMENT);
                config.addMapper(BusinessDataScopeMapper.class);
                String resource="mapper/operation/AmzReplenishmentSnapshotMapper.xml";
                try(var in=getClass().getClassLoader().getResourceAsStream(resource)) {
                    new XMLMapperBuilder(in,config,resource,config.getSqlFragments()).parse();
                }
                try(var session=new SqlSessionFactoryBuilder().build(config).openSession(true))
                {
                    var scopeMapper=session.getMapper(BusinessDataScopeMapper.class);
                    var resolver=new BusinessDataScopeService(scopeMapper);
                    var mapper=session.getMapper(AmzReplenishmentSnapshotMapper.class);
                    var self=resolver.resolve(2L,BusinessDataScopeService.AMZ);
                    assertEquals(List.of("甲"),self.getOwners());
                    assertFalse(self.isAll()); // disabled all-data role cannot widen scope
                    sql.execute("UPDATE sys_user SET nick_name='丙' WHERE user_id=2");
                    assertEquals(List.of("甲"),resolver.resolve(2L,BusinessDataScopeService.AMZ).getOwners());
                    assertTrue(resolver.resolve(2L,BusinessDataScopeService.EBAY).getOwners().isEmpty());
                    sql.execute("INSERT INTO sys_user_role VALUES(2,21)");
                    var dept=resolver.resolve(2L,BusinessDataScopeService.AMZ);
                    assertEquals(Set.of("甲","乙"),new HashSet<>(dept.getOwners()));
                    Map<String,Object> params=new HashMap<>(); params.put("regionGroup","EU");
                    assertTrue(mapper.search(params).isEmpty()); // absent scope denies
                    for (var scope:List.of(self,dept,new BusinessDataScope(true,List.of()),new BusinessDataScope(false,List.of())))
                    {
                        int expected=scope.isAll()?4:scope.getOwners().size();
                        params.put("businessScope",scope);
                        assertEquals(expected,mapper.search(params).size()); // also export SQL
                        assertEquals(expected,mapper.selectDistinctValues("principal_name",null,"EU",scope).size());
                        assertEquals(expected,mapper.selectSalesBreakdown("WAREHOUSE","sales_30d",null,scope).size());
                        params.put("warehouseSkuExact","WAREHOUSE");params.put("breakdownColumn","sales_30d");
                        assertEquals(expected,mapper.selectSalesBreakdownByFilters(params).size());
                        var snap=new AmzReplenishmentSnapshot();snap.setRegionGroup("EU");snap.getParams().put("businessScope",scope);
                        assertEquals(expected,mapper.selectAmzReplenishmentSnapshotList(snap).size());
                    }
                    params.put("businessScope",self);params.put("principalName","乙");
                    assertTrue(mapper.search(params).isEmpty());
                    params.remove("principalName");params.put("businessScope",new BusinessDataScope(false,List.of("x' OR 1=1 --")));
                    assertTrue(mapper.search(params).isEmpty());
                    sql.execute("UPDATE sys_role SET status='1' WHERE role_id IN (20,21)");
                    assertTrue(resolver.resolve(2L,BusinessDataScopeService.AMZ).getOwners().isEmpty());
                }
            }
            finally { sql.execute("DROP DATABASE `"+schema+"`"); }
        }
    }
}
