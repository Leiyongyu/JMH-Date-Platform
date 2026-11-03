# JMH 自定义图标库

业务页面用的自定义图标都放在这个目录，全站可直接复用，不需要再单独引入。

## 怎么用

```vue
<svg-icon icon-class="jmh-export" />
```

- **引用名**：`jmh-` + 文件名（不带 `.svg`）。`vite/plugins/svg-icon.js` 的 `symbolId` 是 `icon-[dir]-[name]`，所以 `jmh/export.svg` 的引用名是 `jmh-export`。
- **颜色**：图标不写死颜色，默认跟随文字颜色（`currentColor`）。用 CSS 的 `color` 设置，例如 `.my-icon { color: #f4ea2a; }`。
- **大小**：默认 `1em`，用 `font-size` 调整，例如 `font-size: 22px`。
- **菜单图标选择器**：只读取上一级 `svg/` 根目录，不会显示这里的业务图标；需要做菜单图标的请放到根目录。

## 新增图标

1. 去掉 svg 里的 `fill` / `width` / `height` / `class` 等属性，只保留 `viewBox` 和 `path`，这样颜色和大小才能由 CSS 控制。
2. 按「用途」命名，用小写英文加连字符，不按来源文件名命名，例如 `refresh.svg`，而不是 `shuaxinanniu.svg`。
3. 在下表登记一行。`tests/jmh-icon-library.test.mjs` 会检查本表和目录里的文件一一对应。

## 图标清单

| 引用名 | 文件 | 用途 | 原始文件 | 页面配色 | 使用位置 |
|---|---|---|---|---|---|
| `jmh-trend-up` | trend-up.svg | 上升 / 比上期增加 | jichu_shangsheng.svg | 红色 `#f56c6c` | AMZ利润报表涨跌 |
| `jmh-trend-down` | trend-down.svg | 下降 / 比上期减少 | shangsheng1.svg（形状为向下箭头） | 绿色 `#67c23a` | AMZ利润报表涨跌 |
| `jmh-export` | export.svg | 导出 Excel / 下载文件 | daochu.svg | 黄色 `#f4ea2a` | AMZ利润报表导出按钮 |
| `jmh-refresh` | refresh.svg | 刷新 / 重新加载 | shuaxinanniu.svg | 黄色 `#f4ea2a` | AMZ利润报表刷新按钮 |
| `jmh-expand` | expand.svg | 展开选项 / 更多设置菜单 | zhankai.svg（原为蓝绿双色，已改为单色） | 蓝色 `#0085D0` | AI助手输入框「数据来源」按钮 |
