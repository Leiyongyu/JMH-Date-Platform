-- 目标库：jmh_data_platform（Java ERP数据库）。
-- 清理已经删除的亚马逊主图批量上传脚本按钮，仅保留图片SOP。

DELETE rm
FROM sys_role_menu rm
JOIN sys_menu m ON m.menu_id=rm.menu_id
WHERE m.perms='sop:amazonImageUpload:use';

DELETE FROM sys_menu
WHERE perms='sop:amazonImageUpload:use'
  AND menu_type='F';

SELECT menu_id,parent_id,menu_name,menu_type,order_num,perms
FROM sys_menu
WHERE perms IN ('sop:scriptTools:view','sop:imageSop:use')
ORDER BY parent_id,order_num,menu_id;
