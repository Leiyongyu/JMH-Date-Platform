// JMH 脚本中心 —— Python 脚本注册表
//
// 新增一个 Python 脚本时，在这里追加一条即可，脚本菜单会自动生成对应的卡片与按钮。
// 可见性由 ERP 的 sys_menu 按钮权限控制（本文件的 permission 字段对应 sys_menu.perms）。
//
// 字段说明：
//   code        唯一标识（用于路由 hash，例如 #/image-sop）
//   name        脚本显示名
//   description 卡片副标题（一句话说明脚本用途）
//   icon        卡片图标（1~2 个字符或 emoji）
//   permission  ERP 按钮权限标识（sys_menu.perms）；空字符串 = 无需权限、所有人可见
//   openMode    打开方式：
//               'embed'      点击后在当前工作台内嵌 iframe 展示
//               'new_window' 点击后在浏览器新标签页打开
//               'redirect'   点击后当前页跳转
//   page        页面路径：
//               - embed：相对代理基址的路径，例如 '/index.html'
//               - new_window / redirect：绝对 URL，或相对 ERP 同源的根路径，例如 '/my-script/'
//   proxyBase   embed 专用：自定义 Java 代理基址（如 '/sop/my-script/proxy'）；
//               留空则使用 ERP 网关注入的 image_proxy_base
//   devBase     embed 专用：本地开发（Vite）时代理基址，例如 '/image-sop'；生产环境忽略
//   needSession embed 专用：是否给页面传递 erp_session（走 Java 安全代理的脚本需为 true）
export default [
  {
    code: 'image-sop',
    name: '图片 SOP',
    description: '生成图片需求，匹配 NAS 素材并导出标准 Excel。',
    icon: 'IS',
    permission: 'sop:imageSop:use',
    openMode: 'embed',
    page: '/index.html',
    proxyBase: '',
    devBase: '/image-sop',
    needSession: true,
  },
]
