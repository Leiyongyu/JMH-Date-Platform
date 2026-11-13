# JMH ERP 前端固定风格（深海蓝 · 潮汐青）

本目录下三份设计稿是项目的**固定视觉规范**，新页面和改动页面一律照此执行：

| 文件 | 内容 |
|---|---|
| `design-proposal.html` | 视觉主题、色板、字体与数字、按钮 / 标签 / 筛选区 / 表格、整页骨架、落地规范 |
| `design-icons.html` | 图标来源规则、图标按钮四尺寸四类型、工具条写法、可用图标总表 |
| `design-icon-v2.html` | 图标库选型（已选 Solar），小尺寸与 BI 大图标的用法 |

代码里的落地位置：`src/assets/styles/tokens.scss`（`--jb-*` 设计变量）、`src/assets/styles/ui.scss`
（表格、分页、卡片、`jb-pill` 状态胶囊）、`src/components/AppIcon`（`<app-icon name="...">`，语义名见
`registry.js`）、`src/components/IconBtn`（`<icon-btn icon="..." tooltip="...">`）。两个组件已在 `main.js` 全局注册。

## 必须遵守

1. **颜色只取变量**：品牌 `--jb-brand-600 #1257D6`（主色）、`--jb-teal-500 #12B2A6`（数据 / 健康状态辅色）；
   文字 `--jb-ink-900/700/500/400`；分隔线 `--jb-line`；页面底色 `--jb-canvas`。不再使用 Element 默认蓝 `#409EFF`、
   紫色渐变或大面积彩色块。语义色：正常 `--jb-ok`、预警 `--jb-warn`、缺货 / 失败 `--jb-danger`；**涨红跌绿**。
2. **页面骨架**固定为：页头（标题 17–20px/600 + 12px 灰色口径说明）→ 指标（可选）→ 筛选 → 数据。
   参照 `views/finance/amzMonthlyProfit/index.vue`：白色 `filter-bar` + `table-card`（`tc-head` 标题、副标题、
   右侧 `chips` 切换与图标按钮，`tc-foot` 口径脚注），右上角问号按钮打开「逻辑与数据来源」抽屉。
3. **表格**：不要 `border` 和 `stripe`，只保留横向细线；表头 11.5px/600、底色 `#F7F9FC`；数值列右对齐并使用
   `font-variant-numeric: tabular-nums`；首列固定；空值显示 `--`，不显示 0 冒充没有数据。
4. **按钮**：每页实心主按钮最多 1 个，其余用描边（ghost）或纯文字；控件高度 32px，紧凑 28px；圆角 4–6px，
   卡片 10–14px；只用极轻投影。
5. **状态**一律用胶囊标签（`jb-pill--ok / warn / danger / info`，或同色系 `el-tag`），带文字，不只靠颜色。
6. **图标**：只写语义名，`<app-icon name="refresh" />`、`<icon-btn icon="export" tooltip="导出" size="sm" />`；
   工具条默认纯图标 + 悬停气泡，图标有歧义时才配文字；业务自定义图标放 `src/assets/icons/svg/jmh/`，
   引用名 `jmh-xxx`。不要再用 `el-button circle` 加边框的圆形按钮排一排。
7. **图表**：主序列 `#1257D6`，辅序列 `#12B2A6`，扩展 `#5B8DEF #0E9E96 #D97706 #7C6CF0 #12A150 #8A99B0`；
   网格线 `#EEF2F8`，不用 3D 和阴影。
8. **深色模式**：底色 `#0B1220`、卡片 `#111C2E`，主色提亮到 `#4D8DF5`，边框 `rgba(255,255,255,.08)`。
9. 抽屉、弹窗挂在 `body` 下取不到页面根变量时，直接写上面的色值。

Solar 图标为 CC BY 4.0 授权，需在致谢中署名 480 Design。
