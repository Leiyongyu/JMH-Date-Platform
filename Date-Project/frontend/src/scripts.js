// JMH Python 脚本注册表。
// 后续新增组件只需追加一项，页面会自动完成权限过滤、分类和卡片布局。
//
// code/permission：唯一标识及对应的 ERP sys_menu.perms。
// category/tags：用于工作台分类和搜索。
// transport：proxy=通过 Java 安全代理；direct=直接地址。
// page/proxyBase/devBase/needSession：组件地址及安全会话配置。
export default [
  {
    code: 'image-sop',
    name: '图片 SOP',
    description: '生成图片需求，匹配 NAS 素材并导出标准 Excel。',
    icon: 'IS',
    category: '图片工具',
    tags: ['NAS 素材', 'Excel 导出', 'Amazon', 'eBay'],
    permission: 'sop:imageSop:use',
    transport: 'proxy',
    page: '/index.html',
    proxyBase: '',
    devBase: '/image-sop',
    needSession: true,
  },
  {
    code: 'daily-workspace',
    name: '每日工作台',
    description: '任务进度跟踪与工作结果导出。',
    icon: 'DW',
    category: '效率工具',
    tags: ['任务管理', 'Excel 导出'],
    permission: 'sop:dailyWorkspace:use',
    transport: 'direct',
    page: '/script-tools/daily-workspace/index.html',
  },
]
