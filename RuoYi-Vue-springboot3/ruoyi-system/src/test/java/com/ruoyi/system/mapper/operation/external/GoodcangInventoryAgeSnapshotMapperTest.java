package com.ruoyi.system.mapper.operation.external;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.InputStream;
import java.util.List;
import java.util.Map;
import org.apache.ibatis.builder.xml.XMLMapperBuilder;
import org.apache.ibatis.mapping.BoundSql;
import org.apache.ibatis.session.Configuration;
import org.junit.jupiter.api.Test;

class GoodcangInventoryAgeSnapshotMapperTest
{
    @Test
    void monthlyAndLatestStatementsTargetSeparateTables() throws Exception
    {
        String resource = "mapper/operation/external/GoodcangInventoryAgeSnapshotMapper.xml";
        Configuration configuration = new Configuration();
        try (InputStream input = getClass().getClassLoader().getResourceAsStream(resource))
        {
            assertThat(input).isNotNull();
            new XMLMapperBuilder(input, configuration, resource,
                    configuration.getSqlFragments()).parse();
        }
        Map<String, Object> parameters = Map.of(
                "snapshotMonth", "2026-09",
                "list", List.of(Map.of("snapshotMonth", "2026-09")));

        assertThat(sql(configuration, "deleteBySnapshotMonth", parameters).getSql())
                .contains("DELETE FROM ods_goodcang_inventory_age_monthly")
                .contains("WHERE snapshot_month = ?")
                .doesNotContain("inventory_age_latest");
        assertThat(sql(configuration, "deleteLatest", parameters).getSql().trim())
                .isEqualTo("DELETE FROM ods_goodcang_inventory_age_latest");
        BoundSql monthly = sql(configuration, "batchInsert", parameters);
        BoundSql latest = sql(configuration, "batchInsertLatest", parameters);
        assertThat(monthly.getSql())
                .contains("INSERT INTO ods_goodcang_inventory_age_monthly")
                .doesNotContain("inventory_age_latest");
        assertThat(latest.getSql())
                .contains("INSERT INTO ods_goodcang_inventory_age_latest")
                .doesNotContain("inventory_age_monthly");
        assertThat(monthly.getParameterMappings()).hasSize(19);
        assertThat(latest.getParameterMappings()).hasSize(19);
        assertThat(latest.getSql().replace("inventory_age_latest", "inventory_age_monthly"))
                .isEqualTo(monthly.getSql());
    }

    private BoundSql sql(Configuration configuration, String statement,
            Map<String, Object> parameters)
    {
        return configuration.getMappedStatement(
                GoodcangInventoryAgeSnapshotMapper.class.getName() + "." + statement)
                .getBoundSql(parameters);
    }
}
