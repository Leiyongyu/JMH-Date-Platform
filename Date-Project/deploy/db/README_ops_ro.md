# ops_ro 只读核对账号

`create_readonly_account.sql` 建一个**只读**账号，供日常核对用（菜单在不在、表建没建、迁移历史、某字段有没有值）。
它不替代任何服务账号；**结构变更一律走 `python -m backend.cli db-migrate`**，否则 `schema_migration_history` 不留记录、
脚本会被重复执行，校验和与失败中止那几道闸也全失效。

权限只有两个库的 `SELECT, SHOW VIEW`（后者用于看维度视图定义，同样不改数据），没有任何 INSERT / UPDATE / DELETE / DDL。

## 执行步骤（部署机 PowerShell）

1. 生成一个 24 位随机密码并复制走，只在本机显示一次：

   ```
   -join ((48..57)+(65..90)+(97..122) | Get-Random -Count 24 | % {[char]$_})
   ```

2. 替换占位符、执行、删临时文件（把 `新密码` 换掉再跑）：

   ```
   $tmp = "$env:TEMP\ops_ro.sql"
   (Get-Content D:\JMH_Project\ops-claude\create_readonly_account.sql -Raw) -replace '<OPS_RO_PASSWORD>','新密码' | Set-Content $tmp -Encoding ascii
   cmd /c "mysql --login-path=jmh_backup < %TEMP%\ops_ro.sql"
   Remove-Item $tmp
   ```

3. 登记 login-path，`--password` 不带值会交互式提示，密码不进命令行历史：

   ```
   mysql_config_editor set --login-path=ops_ro --host=127.0.0.1 --port=3306 --user=ops_ro --password
   ```

4. 验证权限只有只读：

   ```
   mysql --login-path=ops_ro -D "Date-Project" -e "SHOW GRANTS"
   mysql --login-path=ops_ro -D "Date-Project" -e "CREATE TABLE _t(i INT)"
   ```

   第一条应只看到 `USAGE` 加两个库的 `SELECT, SHOW VIEW`；第二条应报 command denied。

回滚：

```
mysql --login-path=jmh_backup -e "DROP USER 'ops_ro'@'localhost', 'ops_ro'@'127.0.0.1'"
mysql_config_editor remove --login-path=ops_ro
```

## 为什么命令写成这个样子

这三行是踩了三个坑之后的结果，改动前请先看完：

1. **不能用 `mysql -e "source 路径"`**。`source` 是客户端命令，经 `-e` 传进去会被当 SQL 发给服务端，
   报 `ERROR 1064 ... near 'source C:/...'`。换成反斜杠路径更糟，`\U` 被当转义符，报 `Unknown command '\U'`。
2. **PowerShell 5.1 不支持 `<` 输入重定向**（保留运算符），所以重定向交给 `cmd /c` 做，
   顺带好处是 mysql 直接读文件字节，PowerShell 不参与解码。
3. **`.sql` 必须是纯 ASCII**。PS 5.1 的 `Get-Content` 按 ANSI 代码页（本机 936）解码，
   UTF-8 的全角字符（比如行尾的 `。`，字节 `E3 80 82`）会让解码器把后面的换行符一起吃掉，两行并成一行。
   `create_readonly_account.sql` 原来带中文注释，结果「注释行 + Date-Project 的 GRANT」并成了一行 148 字符的注释，
   过滤注释时整行被丢掉——**账号会被建成只有 jmh_data_platform 一个库的权限，而且不报任何错**。
   中文说明因此全部挪到本文件，`.sql` 保持 ASCII。
