# Amazon 主图批量上传内嵌说明

## 访问链路

```text
ERP > SOP > 脚本菜单 > 亚马逊主图批量上传
  -> Java 临时会话 / 白名单代理
  -> http://127.0.0.1:8010/amazon-image-upload/
  -> 紫鸟本机 127.0.0.1:16851-16855（最多五个槽位）
  -> Playwright CDP -> Amazon Seller Central
```

浏览器只获得作用域为脚本工具的临时 HttpOnly 会话。Java 代理校验会话后注入
`X-Internal-Token`、`X-Erp-User-ID`、`X-Erp-User` 和 `X-Request-ID`。当前用户的
紫鸟运行快照仅在 Java -> Python 的本机内部请求中传递；密码和 Python
内部令牌不会返回浏览器。

## 数据库边界

- Python 任务、日志、断点表由
  `Date-Project/migrations/20260814_amazon_image_upload.sql` 创建在 `Date-Project` 库。
- ERP 菜单、按钮权限和专用角色由
  `RuoYi-Vue-springboot3/sql/20260814_sop_script_tools_amazon_image_upload.sql`
  创建在 `jmh_data_platform` 库。
- ERP 用户的公司名、紫鸟账号和 `ziniao.exe` 路径由
  `RuoYi-Vue-springboot3/sql/20260814_amazon_image_upload_user_config.sql`
  创建在 `jmh_data_platform` 库。该表没有密码字段。
- 紫鸟密码只以 ERP `user_id` 为作用域缓存在 Redis，固定 8 小时过期，
  使用过程不会续期。
- 两套表不能交叉创建。

## 必需环境变量

```dotenv
PYTHON_INTERNAL_API_TOKEN=Java与Python共用的内部长随机令牌
AMAZON_IMAGE_UPLOAD_ZINIAO_PORT=16851
AMAZON_IMAGE_UPLOAD_SHOP_ROOT=D:\Amazon主图上传
```

`AMAZON_IMAGE_UPLOAD_ZINIAO_PORT` 是起始端口，程序固定使用连续五个端口；
第六个及后续 Amazon 自动化任务进入 FIFO 队列，前端会显示排队位置。
排队只保留进程内运行快照；Redis 密码剩余有效期到达时会立即清空快照并取消该排队任务。
Windows 防火墙不需要对外开放这些端口，它们只监听本机回环地址。

公司名、账号、密码和紫鸟路径由每个用户在 ERP「SOP > 脚本菜单 > 配置」
中输入。`AMAZON_IMAGE_UPLOAD_ZINIAO_COMPANY/USERNAME/CLIENT_PATH`
仅作为不经 ERP 代理的本机开发回退值，生产 ERP 流程不依赖它们。
Python 不再读取 `AMAZON_IMAGE_UPLOAD_ZINIAO_PASSWORD`，密码没有任何文件或环境变量回退通道。

可通过 `AMAZON_IMAGE_UPLOAD_OUTPUT_DIR` 修改运行输出目录，默认是
`Date-Project/outputs/amazon_image_upload`。该目录只保存临时数据和诊断文件，
已经由仓库 `.gitignore` 排除。

## 固定店铺目录和权限初始化

生产环境必须把 `AMAZON_IMAGE_UPLOAD_SHOP_ROOT` 指向 Windows 执行主机上的固定绝对路径。
用户打开工具后，Python 使用该用户在 Redis 中的紫鸟密码登录紫鸟，只读取该账号可见店铺，
然后按以下规则自动创建缺失目录：

```text
D:\Amazon主图上传\
  <安全化店铺名>__<店铺ID的12位SHA-256>\
    sku.xlsx                 # 人工放置，xlsx/xlsm均可
    图片\
      <SKU>\
        01.jpg
        02.jpg
```

哈希后缀用于区分同名店铺并在店铺改名后复用原目录。浏览器不能提交任意服务器路径；
批量图片接口只接受当前 ERP 用户本次紫鸟初始化得到的店铺 ID，目标路径由服务器计算。
单张图片最大 30MB，前端按最多 50 个文件且不超过 45MB 自动拆批。默认不覆盖同名文件；
同一店铺的写入串行并通过临时文件 + `os.replace` 原子落盘，不同店铺可并行上传。
每个批次写入 `Date-Project.amazon_image_upload_file_batch` 审计表，不记录密码。

Java 默认连接 `http://127.0.0.1:8010/amazon-image-upload`。Python 不在 Java 本机时，
可设置：

```dotenv
AMAZON_IMAGE_UPLOAD_PYTHON_BASE_URL=http://Python主机:8010/amazon-image-upload
```

## 部署要求

1. 安装 Python 新依赖：`pip install -r backend/requirements.txt`。
2. 在 Python 的 `.env` 配置内部令牌、固定店铺根目录和紫鸟起始端口。
3. 启动 Python 时会在 `Date-Project` 数据库自动执行
   `migrations/20260814_amazon_image_upload.sql`，创建任务、五槽位执行器和图片批次审计表；
   也可在停机维护时手动执行该文件。
4. 在 `jmh_data_platform` 执行菜单 SQL 和用户配置表 SQL。
5. 确认 ERP 的 Redis 正常可用，重启 Python、Java 并重新构建 ERP 前端。
6. 重新登录 ERP，进入脚本菜单，由当前用户点击「配置」录入紫鸟信息。

该工具必须运行在安装紫鸟且具有可交互 Windows 桌面的执行主机上。不要把 Python
作为不可交互的 Session 0 服务运行，否则紫鸟窗口可能不可见；推荐以登录用户启动
Python，或使用计划任务并选择“仅在用户登录时运行”。代码最多分配五个独立端口；
紫鸟客户端版本和企业授权也必须支持同机多实例，否则对应任务会失败并在任务日志中说明。

旧项目的 `config.yaml`、浏览器 Profile、Cookie、真实图片/Excel、日志和截图均未迁移，
也不应提交到仓库。
