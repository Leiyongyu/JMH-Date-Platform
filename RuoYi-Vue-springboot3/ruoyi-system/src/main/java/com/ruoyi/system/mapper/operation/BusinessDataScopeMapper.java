package com.ruoyi.system.mapper.operation;

import java.util.List;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Delete;
import org.apache.ibatis.annotations.Insert;

public interface BusinessDataScopeMapper
{
    @Select("""
        SELECT DISTINCT m.perms FROM sys_user u
        JOIN sys_user_role ur ON ur.user_id=u.user_id
        JOIN sys_role r ON r.role_id=ur.role_id AND r.status='0' AND r.del_flag='0'
        JOIN sys_role_menu rm ON rm.role_id=r.role_id
        JOIN sys_menu m ON m.menu_id=rm.menu_id AND m.status='0'
        WHERE u.user_id=#{userId} AND u.status='0' AND u.del_flag='0'
        """)
    List<String> permissions(@Param("userId") Long userId);

    // Administrator-maintained identity binding, never the user's editable nickname.
    @Select("""
        SELECT DISTINCT binding.owner_name FROM sys_user actor JOIN sys_user member
        ON (member.user_id=actor.user_id OR (#{department}=TRUE AND member.dept_id=actor.dept_id
            AND actor.dept_id IS NOT NULL AND actor.dept_id != 0))
        JOIN sys_business_owner_binding binding ON binding.user_id=member.user_id
        WHERE actor.user_id=#{userId} AND actor.status='0' AND actor.del_flag='0'
          AND member.status='0' AND member.del_flag='0'
        """)
    List<String> ownerNames(@Param("userId") Long userId, @Param("department") boolean department);

    @Select("SELECT owner_name FROM sys_business_owner_binding WHERE user_id=#{userId} ORDER BY owner_name")
    List<String> bindings(@Param("userId") Long userId);

    @Delete("DELETE FROM sys_business_owner_binding WHERE user_id=#{userId}")
    int deleteBindings(@Param("userId") Long userId);

    @Insert("INSERT INTO sys_business_owner_binding(user_id,owner_name) VALUES(#{userId},#{name})")
    int insertBinding(@Param("userId") Long userId, @Param("name") String name);

    @Select("""
        SELECT principal_name FROM (
          SELECT sid,seller_sku,principal_name,current_flag FROM amz_replenishment_us_snapshot
          UNION ALL SELECT sid,seller_sku,principal_name,current_flag FROM amz_replenishment_eu_snapshot
        ) s WHERE s.current_flag=1 AND s.sid=#{sid} AND BINARY s.seller_sku=BINARY #{sku}
        """)
    List<String> amzRowOwners(@Param("sid") String sid, @Param("sku") String sku);
}
