"""亚马逊卖家后台浏览器自动化核心（Playwright + 紫鸟浏览器）。



说明：

- 通过紫鸟浏览器启动店铺，获取 CDP 调试端口，用 Playwright connect_over_cdp 连接。

- 登录态由紫鸟浏览器管理（每个店铺独立指纹/Cookie/IP），无需本地持久化。

- 亚马逊后台页面结构会随站点/版本变化，选择器采用「主选择器 + 多重兜底」策略。

- 如某步骤定位失败，日志会打印当前 URL、页面标题、截图路径，便于排查和调整选择器。

"""

from __future__ import annotations



import asyncio

import os

import random

from datetime import datetime

from typing import Any



from loguru import logger

from playwright.async_api import (

    Browser,

    BrowserContext,

    Page,

    Playwright,

    async_playwright,

)



# 诊断文件只写入运行输出目录，不写入源码目录，也不迁移旧项目 Cookie/Profile。

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SCREENSHOT_DIR = os.getenv(
    "AMAZON_IMAGE_UPLOAD_DIAGNOSTIC_DIR",
    os.path.join(_PROJECT_ROOT, "outputs", "amazon_image_upload", "diagnostics"),
)





class AmazonBot:

    """封装亚马逊后台主图上传的全部浏览器操作。"""



    def __init__(self, cfg: dict[str, Any]):

        self.cfg = cfg

        self.browser_cfg = cfg.get("browser", {}) or {}

        self.timeout = int(self.browser_cfg.get("timeout", 30000))

        self.slow_mo = int(self.browser_cfg.get("slow_mo", 300))

        self.retry_times = int(self.browser_cfg.get("retry_times", 3))



        self._pw: Playwright | None = None

        self._browser: Browser | None = None

        self._context: BrowserContext | None = None

        self._page: Page | None = None

        self._orig_page: Page | None = None  # 管理图片打开前的原标签页（库存页）



    # ------------------------------------------------------------------

    # 生命周期

    # ------------------------------------------------------------------

    async def start(self, debugging_port: int) -> None:

        """通过 CDP 端口连接紫鸟浏览器已启动的店铺窗口。"""

        logger.info("连接紫鸟浏览器 (CDP端口={})", debugging_port)

        try:

            self._pw = await async_playwright().start()

            self._browser = await self._pw.chromium.connect_over_cdp(

                f"http://127.0.0.1:{debugging_port}"

            )

        except BaseException:

            if self._pw:

                await self._pw.stop()

            self._pw = None

            self._browser = None

            raise

        self._context = self._browser.contexts[0] if self._browser.contexts else await self._browser.new_context()

        self._context.set_default_timeout(self.timeout)

        self._page = self._context.pages[0] if self._context.pages else await self._context.new_page()

        logger.info("已连接紫鸟浏览器")



    async def close(self) -> None:

        """断开 Playwright 与紫鸟浏览器的连接（不关闭浏览器窗口）。"""

        if self._browser:

            await self._browser.close()

        if self._pw:

            await self._pw.stop()

        self._browser = None

        self._pw = None

        self._context = None

        self._page = None

        logger.info("已断开紫鸟浏览器连接")



    @property

    def page(self) -> Page:

        if self._page is None:

            raise RuntimeError("浏览器未启动，请先调用 start()")

        return self._page



    # ------------------------------------------------------------------

    # 诊断工具

    # ------------------------------------------------------------------

    async def _diagnose(self, prefix: str = "诊断") -> None:

        """打印当前页面诊断信息并截图。"""

        try:

            url = self.page.url

            title = await self.page.title()

            logger.error("{} | URL={} | Title={}", prefix, url, title)

            # 截图

            os.makedirs(SCREENSHOT_DIR, exist_ok=True)

            ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")

            path = os.path.join(SCREENSHOT_DIR, f"{prefix.replace(' ', '_')}_{ts}.png")

            await self.page.screenshot(path=path, full_page=True)

            logger.error("{} | 已保存截图: {}", prefix, os.path.abspath(path))

            # 打印部分可见文本

            body_text = await self.page.locator("body").inner_text()

            snippet = " ".join(body_text.split())[:400]

            logger.error("{} | 页面文本片段: {}", prefix, snippet)

        except Exception as e:

            logger.error("{} | 诊断信息获取失败: {}", prefix, e)



    async def _dump_html(self, sku: str) -> None:

        """导出页面 HTML + 所有按钮详细信息到文件，方便调试选择器。"""

        try:

            os.makedirs(SCREENSHOT_DIR, exist_ok=True)

            ts = datetime.now().strftime("%Y%m%d_%H%M%S")



            # 1. 导出完整页面 HTML

            html_path = os.path.join(SCREENSHOT_DIR, f"page_html_{ts}.html")

            full_html = await self.page.content()

            with open(html_path, "w", encoding="utf-8") as f:

                f.write(full_html)

            logger.error("已导出页面 HTML 到: {}", os.path.abspath(html_path))



            # 2. 导出所有可见可点击元素的详细信息

            btn_info = await self.page.evaluate(

                """() => {

                    const results = [];

                    const all = document.querySelectorAll(

                        'button, [role="button"], a, kat-dropdown-button, [class*="action"], [class*="menu"], [class*="overflow"], [class*="trigger"], [data-action], [data-testid*="action"], [data-testid*="menu"]'

                    );

                    for (const b of all) {

                        const rect = b.getBoundingClientRect();

                        if (rect.width === 0 || rect.height === 0) continue;

                        let nearbyText = '';

                        let parent = b.parentElement;

                        for (let i = 0; i < 3 && parent; i++) {

                            nearbyText = parent.innerText.substring(0, 100);

                            if (nearbyText.trim()) break;

                            parent = parent.parentElement;

                        }

                        results.push({

                            tag: b.tagName,

                            class: b.className.substring(0, 200),

                            id: b.id || '',

                            ariaLabel: b.getAttribute('aria-label') || '',

                            ariaHaspopup: b.getAttribute('aria-haspopup') || '',

                            ariaExpanded: b.getAttribute('aria-expanded') || '',

                            dataTestId: b.getAttribute('data-testid') || '',

                            dataAction: b.getAttribute('data-action') || '',

                            title: b.getAttribute('title') || '',

                            text: (b.innerText || '').substring(0, 80),

                            html: b.outerHTML.substring(0, 500),

                            nearbyText: nearbyText.replace(/\\n/g, ' ').substring(0, 100),

                            hasSvg: b.querySelector('svg') !== null,

                            svgClass: (b.querySelector('svg') || {}).className || '',

                            x: Math.round(rect.x),

                            y: Math.round(rect.y),

                            w: Math.round(rect.width),

                            h: Math.round(rect.height),

                        });

                    }

                    return results;

                }"""

            )

            btn_path = os.path.join(SCREENSHOT_DIR, f"buttons_info_{ts}.txt")

            with open(btn_path, "w", encoding="utf-8") as f:

                f.write(f"页面按钮诊断 (SKU={sku})\n")

                f.write(f"时间: {ts}\n")

                f.write(f"URL: {self.page.url}\n")

                f.write(f"按钮总数: {len(btn_info)}\n")

                f.write("=" * 80 + "\n\n")

                for i, b in enumerate(btn_info):

                    f.write(f"--- 按钮 #{i} ---\n")

                    f.write(f"  位置: ({b['x']}, {b['y']}) 尺寸: {b['w']}x{b['h']}\n")

                    f.write(f"  tag: {b['tag']}  id: {b['id']}\n")

                    f.write(f"  class: {b['class']}\n")

                    f.write(f"  aria-label: {b['ariaLabel']}\n")

                    f.write(f"  aria-haspopup: {b['ariaHaspopup']}\n")

                    f.write(f"  aria-expanded: {b['ariaExpanded']}\n")

                    f.write(f"  data-testid: {b['dataTestId']}\n")

                    f.write(f"  data-action: {b['dataAction']}\n")

                    f.write(f"  title: {b['title']}\n")

                    f.write(f"  text: {b['text']}\n")

                    f.write(f"  hasSvg: {b['hasSvg']}  svgClass: {b['svgClass']}\n")

                    f.write(f"  nearbyText: {b['nearbyText']}\n")

                    f.write(f"  html: {b['html']}\n\n")

            logger.error("已导出按钮信息到: {}", os.path.abspath(btn_path))



            # 3. 特别标注"预计"附近的按钮

            near_price = [b for b in btn_info if "预计" in b.get("nearbyText", "") or "预计" in b.get("text", "")]

            if near_price:

                with open(btn_path, "a", encoding="utf-8") as f:

                    f.write("\n" + "=" * 80 + "\n")

                    f.write(">>> 「预计」文字附近的按钮（最可能是三个点操作菜单）：\n")

                    f.write("=" * 80 + "\n\n")

                    for b in near_price:

                        f.write(f"  位置: ({b['x']}, {b['y']}) 尺寸: {b['w']}x{b['h']}\n")

                        f.write(f"  class: {b['class']}\n")

                        f.write(f"  aria-label: {b['ariaLabel']}\n")

                        f.write(f"  aria-haspopup: {b['ariaHaspopup']}\n")

                        f.write(f"  html: {b['html']}\n\n")

                logger.error(">>> 在 buttons_info 文件末尾标注了「预计」附近的按钮")



            logger.error("请把这两个文件发给我:")

            logger.error("  1. {}", os.path.abspath(html_path))

            logger.error("  2. {}", os.path.abspath(btn_path))

        except Exception as e:

            logger.error("导出 HTML 失败: {}", e)



    async def _dump_manage_images_page_info(self, context: str = "") -> None:

        """【无条件导出】管理图片页面的全部交互元素信息 + 截图 + HTML。



        不管后续操作成功还是失败，都先调用此方法把页面信息保存到

        logs/screenshots 目录，方便对照亚马逊实际 DOM 修选择器。



        Args:

            context: 标记本次导出的场景（如 "清理前" "上传前"）

        """

        try:

            os.makedirs(SCREENSHOT_DIR, exist_ok=True)

            ts = datetime.now().strftime("%Y%m%d_%H%M%S")

            tag = f"manage_images_{context}_{ts}" if context else f"manage_images_{ts}"



            # 1. 截图

            shot_path = os.path.join(SCREENSHOT_DIR, f"{tag}.png")

            await self.page.screenshot(path=shot_path, full_page=True)

            logger.info("[页面诊断] 截图已保存: {}", os.path.abspath(shot_path))



            # 2. 导出 HTML

            html_path = os.path.join(SCREENSHOT_DIR, f"{tag}.html")

            full_html = await self.page.content()

            with open(html_path, "w", encoding="utf-8") as f:

                f.write(full_html)

            logger.info("[页面诊断] HTML 已保存: {}", os.path.abspath(html_path))



            # 3. 导出所有可见交互元素的详细信息

            elements_info = await self.page.evaluate(

                """() => {

                    const results = [];

                    const safeGet = (obj, key, dflt) => {

                        try { const v = obj && obj[key]; return (v === undefined || v === null) ? dflt : v; }

                        catch (e) { return dflt; }

                    };

                    const safeStr = (v, max) => {

                        try { return v == null ? '' : String(v).substring(0, max); }

                        catch (e) { return ''; }

                    };

                    // 扫描所有可能可交互的元素

                    const selectors = 'button, [role="button"], a, input, kat-icon-button, kat-button, kat-dropdown-button, [class*="action"], [class*="icon"], [class*="close"], [class*="remove"], [class*="delete"], [class*="trash"], [data-testid], [data-action], [title], [aria-label]';

                    const all = document.querySelectorAll(selectors);

                    for (const el of all) {

                        const rect = el.getBoundingClientRect();

                        if (rect.width === 0 || rect.height === 0) continue;

                        const style = window.getComputedStyle(el);

                        if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') continue;



                        // 判断是否在含 uploaded-image 的容器内

                        let inImageArea = false;

                        let p = el;

                        while (p && p !== document.body) {

                            const cls = safeStr(p.className);

                            if (cls.indexOf('imageArea') !== -1 || cls.indexOf('img-section') !== -1) {

                                inImageArea = true;

                                break;

                            }

                            p = p.parentElement;

                        }



                        // 判断附近是否有 uploaded-image

                        let nearUploaded = false;

                        let parent = el.parentElement;

                        for (let i = 0; i < 4 && parent; i++) {

                            if (parent.querySelector('img.uploaded-image, img[class*="uploaded"]')) {

                                nearUploaded = true;

                                break;

                            }

                            parent = parent.parentElement;

                        }



                        // 提取子元素信息时全部用 try/catch 包裹（kat-icon 等自定义组件可能没有这些属性/方法）

                        let svgClass = '', imgSrc = '', hasSvg = false, hasImg = false;

                        try {

                            const svg = el.querySelector('svg');

                            if (svg) { hasSvg = true; svgClass = safeStr(svg.className, 100); }

                        } catch (e) { /* ignore */ }

                        try {

                            const img = el.querySelector('img');

                            if (img) { hasImg = true; imgSrc = safeStr(img.getAttribute && img.getAttribute('src'), 80); }

                        } catch (e) { /* ignore */ }



                        results.push({

                            tag: el.tagName,

                            class: safeStr(el.className, 200),

                            id: el.id || '',

                            ariaLabel: el.getAttribute('aria-label') || '',

                            role: el.getAttribute('role') || '',

                            dataTestId: el.getAttribute('data-testid') || '',

                            dataAction: el.getAttribute('data-action') || '',

                            title: el.getAttribute('title') || '',

                            icon: el.getAttribute('icon') || '',

                            text: ((el.innerText || el.value || '') + '').substring(0, 60),

                            html: safeStr(el.outerHTML, 300),

                            hasSvg: hasSvg,

                            svgClass: svgClass,

                            hasImg: hasImg,

                            imgSrc: imgSrc,

                            x: Math.round(rect.x),

                            y: Math.round(rect.y),

                            w: Math.round(rect.width),

                            h: Math.round(rect.height),

                            inImageArea: inImageArea,

                            nearUploaded: nearUploaded,

                        });

                    }

                    return results;

                }"""

            )



            info_path = os.path.join(SCREENSHOT_DIR, f"{tag}_elements.txt")

            with open(info_path, "w", encoding="utf-8") as f:

                f.write(f"管理图片页面元素诊断\n")

                f.write(f"时间: {ts}\n")

                f.write(f"URL: {self.page.url}\n")

                f.write(f"交互元素总数: {len(elements_info)}\n")

                f.write("=" * 100 + "\n\n")



                # 先列出在 imageArea 内或附近有 uploaded-image 的元素（最可能是删除按钮）

                image_related = [e for e in elements_info if e["inImageArea"] or e["nearUploaded"]]

                f.write(f">>> 在 imageArea 内或附近有 uploaded-image 的元素 ({len(image_related)} 个) <<<\n")

                f.write("=" * 100 + "\n\n")

                for i, e in enumerate(image_related):

                    f.write(f"--- #{i} inImageArea={e['inImageArea']} nearUploaded={e['nearUploaded']} ---\n")

                    f.write(f"  位置: ({e['x']}, {e['y']})  尺寸: {e['w']}x{e['h']}\n")

                    f.write(f"  tag={e['tag']}  id={e['id']}  role={e['role']}\n")

                    f.write(f"  class: {e['class']}\n")

                    f.write(f"  aria-label: {e['ariaLabel']}\n")

                    f.write(f"  data-testid: {e['dataTestId']}  data-action: {e['dataAction']}\n")

                    f.write(f"  title: {e['title']}  icon: {e['icon']}\n")

                    f.write(f"  text: {e['text']}\n")

                    f.write(f"  hasSvg={e['hasSvg']} svgClass={e['svgClass']} hasImg={e['hasImg']}\n")

                    f.write(f"  html: {e['html']}\n\n")



                # 然后列出所有其他元素

                others = [e for e in elements_info if not e["inImageArea"] and not e["nearUploaded"]]

                f.write(f"\n{'=' * 100}\n")

                f.write(f">>> 其他交互元素 ({len(others)} 个) <<<\n")

                f.write("=" * 100 + "\n\n")

                for i, e in enumerate(others):

                    f.write(f"--- #{i} ---\n")

                    f.write(f"  位置: ({e['x']}, {e['y']})  尺寸: {e['w']}x{e['h']}\n")

                    f.write(f"  tag={e['tag']}  id={e['id']}  class={e['class'][:80]}\n")

                    f.write(f"  aria-label: {e['ariaLabel']}  title: {e['title']}  text: {e['text'][:30]}\n")

                    f.write(f"  html: {e['html'][:150]}\n\n")



            logger.info("[页面诊断] 元素信息已保存: {} (共 {} 个元素, {} 个在图片区域内)",

                        os.path.abspath(info_path), len(elements_info), len(image_related))

            logger.info("[页面诊断] 请把以上 3 个文件发给我以便分析:")

            logger.info("  1. {}", os.path.abspath(shot_path))

            logger.info("  2. {}", os.path.abspath(html_path))

            logger.info("  3. {}", os.path.abspath(info_path))

        except Exception as e:

            logger.error("[页面诊断] 导出失败: {}", e)



    # ------------------------------------------------------------------

    # 导航与登录

    # ------------------------------------------------------------------

    async def _wait_inventory_ready(self, timeout_sec: int = 20) -> None:

        """等待库存页关键元素渲染完成（搜索框 / 库存表格）。



        Amazon 库存页是重 SPA，domcontentloaded 触发时表格和搜索框还没渲染。

        此方法依次尝试：networkidle → 等搜索框出现 → 兜底 sleep。

        """

        # 1. 等 networkidle（最多 15s，超时忽略）

        try:

            await self.page.wait_for_load_state("networkidle", timeout=15000)

            logger.info("库存页 networkidle 完成")

        except Exception:

            logger.info("networkidle 超时，继续等待选择器...")



        # 2. 等搜索框或库存表格出现（最多 timeout_sec 秒）

        ready_selectors = [

            'input[placeholder*="搜索"]',

            'input[placeholder*="SKU"]',

            'input[placeholder*="Search"]',

            'input[type="search"]',

            "#inventory-search-filter",

            'table',

            '[data-testid*="inventory"]',

            '[class*="inventory-list"]',

        ]

        deadline = asyncio.get_event_loop().time() + timeout_sec

        found = False

        while asyncio.get_event_loop().time() < deadline:

            for sel in ready_selectors:

                try:

                    loc = self.page.locator(sel).first

                    if await loc.count() > 0 and await loc.is_visible():

                        found = True

                        logger.info("库存页关键元素已出现: {}", sel)

                        break

                except Exception:

                    continue

            if found:

                break

            await asyncio.sleep(1)



        if not found:

            logger.warning("库存页等待 {}s 后仍未检测到关键元素，兜底等待 3s", timeout_sec)

            await asyncio.sleep(3)

        else:

            # 元素出现后再给一点渲染缓冲

            await asyncio.sleep(1)



    async def open_inventory(self, domain: str) -> bool:

        """打开某站点的「管理所有库存」页面。



        流程：导航到库存页 URL → 如果遇到登录/验证码页面则自动处理 →

        登录完成后重新导航到库存页 → 确认已进入后台。

        """

        url = f"https://{domain}/inventory?viewId=LISTINGS"

        logger.info("打开库存页: {}", url)

        try:

            await self.page.goto(url, wait_until="domcontentloaded")

            await self._wait_inventory_ready()

        except Exception as e:

            logger.error("打开库存页失败: {}", e)

            await self._diagnose("打开库存页失败")

            return False



        # 检查是否被重定向到登录页面

        if await self._is_login_page():

            logger.warning("检测到登录/验证码页面，开始自动处理登录...")

            logged_in = await self.handle_login_if_needed(domain)

            if not logged_in:

                logger.error("自动登录处理失败")

                await self._diagnose("登录失败")

                return False



            # 登录完成后重新导航到库存页

            logger.info("登录完成，重新打开库存页: {}", url)

            try:

                await self.page.goto(url, wait_until="domcontentloaded")

                await self._wait_inventory_ready()

            except Exception as e:

                logger.error("重新打开库存页失败: {}", e)

                await self._diagnose("重新打开库存页失败")

                return False



            # 再次确认已进入后台

            if await self._is_login_page():

                logger.error("登录后仍在登录页面，可能需要手动处理验证码")

                await self._diagnose("登录后仍在登录页")

                return False

        else:

            logger.info("已在卖家后台，无需登录")



        return True



    async def _is_login_page(self) -> bool:

        """检测当前页面是否为亚马逊登录/验证码页面。"""

        try:

            cur = self.page.url.lower()

            if "signin" in cur or "ap/signin" in cur or "/ap/" in cur:

                return True

            # 检查是否有邮箱/密码输入框（登录页特征）

            email_count = await self.page.locator(

                'input[type="email"], input[name="email"], input[id*="email" i], #ap_email'

            ).count()

            if email_count > 0:

                return True

            # 检查是否有密码输入框

            pwd_count = await self.page.locator(

                'input[type="password"], input[name="password"], #ap_password'

            ).count()

            if pwd_count > 0:

                return True

            return False

        except Exception:

            return False



    async def handle_login_if_needed(self, domain: str) -> bool:

        """自动处理亚马逊登录/验证码流程。



        流程（根据用户描述）：

        1. 检测到登录页面

        2. 第一次点击"登录"按钮

        3. 等待页面加载，出现二次确认页面

        4. 稍等验证码自动载入

        5. 第二次点击"登录"按钮

        6. 等待跳转到卖家后台完成

        """

        logger.info("=== 开始自动登录处理 ===")



        # Step 1: 第一次点击登录按钮

        logger.info("[1/4] 第一次点击登录按钮...")

        clicked_1 = await self._click_login_button()

        if not clicked_1:

            logger.warning("第一次未找到登录按钮，等待页面变化后重试...")

            await asyncio.sleep(3)

            clicked_1 = await self._click_login_button()

            if not clicked_1:

                logger.error("无法找到登录按钮，请检查页面是否需要手动输入")

                await self._diagnose("登录_未找到登录按钮")

                return False



        # Step 2: 等待页面加载（二次确认页面）

        logger.info("[2/4] 等待二次确认页面加载...")

        await asyncio.sleep(3)

        try:

            await self.page.wait_for_load_state("domcontentloaded", timeout=15000)

        except Exception:

            logger.warning("页面加载等待超时，继续执行")

        await asyncio.sleep(2)



        # Step 3: 等待验证码自动载入

        logger.info("[3/4] 等待验证码自动载入...")

        # 给验证码图片/组件充分的时间加载

        await asyncio.sleep(5)



        # 检查是否还需要第二次点击

        if not await self._is_login_page():

            logger.info("页面已跳转，无需第二次点击登录")

            logger.info("=== 自动登录处理完成 ===")

            return await self._wait_login_complete(domain)



        # Step 4: 第二次点击登录按钮

        logger.info("[4/4] 第二次点击登录按钮...")

        clicked_2 = await self._click_login_button()

        if not clicked_2:

            logger.warning("第二次未找到登录按钮，可能页面已自动提交")

            await asyncio.sleep(3)

        else:

            await asyncio.sleep(2)



        # 等待跳转到卖家后台

        success = await self._wait_login_complete(domain)

        if success:

            logger.info("=== 自动登录处理完成 ===")

        else:

            logger.error("=== 自动登录处理超时 ===")

        return success



    async def _click_login_button(self) -> bool:

        """查找并点击登录/Sign In 按钮。"""

        # 登录按钮的各种文本（中文/英文）

        login_texts = [

            "登录", "登 录", "Sign In", "Sign in", "signin",

            "Continue", "继续", "Next", "下一步", "Submit", "提交",

        ]



        # 方式1: 通过文本匹配点击

        for text in login_texts:

            for sel in [

                f'button:has-text("{text}")',

                f'a:has-text("{text}")',

                f'[role="button"]:has-text("{text}")',

                f'input[value="{text}"]',

            ]:

                try:

                    loc = self.page.locator(sel).first

                    if await loc.count() > 0 and await loc.is_visible():

                        await loc.click(timeout=5000)

                        logger.info("点击登录按钮: {} ({})", text, sel)

                        return True

                except Exception:

                    continue



        # 方式2: 亚马逊登录页常用 ID

        for sel in [

            '#signInSubmit',

            '#continue',

            '#login',

            'input[type="submit"]',

            'button[type="submit"]',

            'kat-button:has-text("登录")',

            'kat-button:has-text("Sign")',

        ]:

            try:

                loc = self.page.locator(sel).first

                if await loc.count() > 0 and await loc.is_visible():

                    await loc.click(timeout=5000)

                    logger.info("点击登录按钮 (selector={})", sel)

                    return True

            except Exception:

                continue



        # 方式3: JS 兜底——扫描所有可点击元素找登录按钮

        try:

            result = await self.page.evaluate(

                """() => {

                    const candidates = [

                        ...document.querySelectorAll('input[type="submit"]'),

                        ...document.querySelectorAll('button[type="submit"]'),

                        ...document.querySelectorAll('button'),

                        ...document.querySelectorAll('a[role="button"]'),

                        ...document.querySelectorAll('[role="button"]'),

                        ...document.querySelectorAll('kat-button'),

                    ];

                    const loginTexts = ['登录', '登 录', 'Sign In', 'Sign in', 'signin',

                                       'Continue', '继续', 'Next', '下一步', 'Submit', '提交'];

                    for (const b of candidates) {

                        const text = (b.innerText || b.value || '').trim();

                        for (const lt of loginTexts) {

                            if (text === lt || text.includes(lt)) {

                                const rect = b.getBoundingClientRect();

                                if (rect.width > 0 && rect.height > 0) {

                                    b.click();

                                    return {ok: true, text: text};

                                }

                            }

                        }

                    }

                    return {ok: false};

                }"""

            )

            if result and result.get("ok"):

                logger.info("JS 兜底点击登录按钮: {}", result.get("text"))

                return True

        except Exception as e:

            logger.warning("JS 兜底点击登录按钮失败: {}", e)



        logger.warning("未找到登录按钮")

        return False



    async def _wait_login_complete(self, domain: str, timeout_sec: int = 120) -> bool:

        """等待登录完成，页面跳转到卖家后台。"""

        logger.info("等待跳转到卖家后台 ({})...", domain)

        start = asyncio.get_event_loop().time()

        while asyncio.get_event_loop().time() - start < timeout_sec:

            await asyncio.sleep(2)

            cur = self.page.url

            # 检查是否已跳转到卖家后台

            if domain in cur and "signin" not in cur and "ap/" not in cur:

                logger.info("已跳转到卖家后台: {}", cur)

                return True

            # 检查是否已离开登录页

            if not await self._is_login_page():

                logger.info("已离开登录页面: {}", cur)

                return True

        logger.warning("等待登录完成超时（{}秒），当前 URL: {}", timeout_sec, self.page.url)

        return False



    # ------------------------------------------------------------------

    # 工具方法

    # ------------------------------------------------------------------

    async def _retry(self, fn, *args, **kwargs):

        """带重试的异步调用。"""

        last_err: Exception | None = None

        for attempt in range(1, self.retry_times + 1):

            try:

                return await fn(*args, **kwargs)

            except Exception as e:  # noqa: BLE001

                last_err = e

                logger.warning("第 {} 次尝试失败: {}", attempt, e)

                await asyncio.sleep(1.5 * attempt)

        raise last_err  # type: ignore[misc]



    async def _click_text(self, candidates: list[str], timeout: int | None = None) -> bool:

        """按文本候选列表点击第一个匹配的按钮/链接/菜单项。"""

        to = timeout if timeout is not None else self.timeout

        for text in candidates:

            for sel in [

                f'button:has-text("{text}")',

                f'a:has-text("{text}")',

                f'[role="button"]:has-text("{text}")',

                f'kat-button:has-text("{text}")',

                f'kat-dropdown-item:has-text("{text}")',

                f'div:has-text("{text}")',

                f'span:has-text("{text}")',

            ]:

                loc = self.page.locator(sel).first

                try:

                    if await loc.count() > 0 and await loc.is_visible():

                        await loc.click(timeout=to)

                        logger.info("点击: {} ({})", text, sel)

                        return True

                except Exception:

                    continue

        logger.warning("未找到可点击元素: {}", candidates)

        return False



    # ------------------------------------------------------------------

    # 图片占位清理（上传前清空已有的旧图片）

    # ------------------------------------------------------------------

    async def clear_image_widgets(self) -> int:

        """在上传新图片前，先清空页面上所有已上传的旧图片。



        改进版修复：

        1. 先 hover 到每张图片上，触发删除按钮显示（亚马逊后台删除按钮默认隐藏）

        2. 增强删除按钮识别策略，扩大图片区域搜索层级

        3. 使用 Playwright locator 点击替代坐标点击，更精准

        4. 删除后验证图片确实消失

        5. 增加多种删除按钮选择器兜底



        Returns:

            被清理的图片数量（0 表示页面本来无旧图）。

        """

        logger.info("=== 开始清理已有图片 ===")



        # ── Step 0: 无条件导出页面信息（不管后续成功失败都保存）──

        # 已注释掉清理前的页面导出，提升速度
        # await self._dump_manage_images_page_info("清理前")

        # ★ 直接滚动到页面底部，所有操作都在底部完成
        try:
            await self.page.evaluate("() => { window.scrollTo(0, document.body.scrollHeight); }")
            await asyncio.sleep(0.8)
        except Exception:
            pass
            await asyncio.sleep(0.5)

        except Exception:

            pass



        # ── Step 1: 先统计初始有多少张已上传图片 ──

        initial_count = await self._count_uploaded_images()

        logger.info("页面初始已上传图片数量: {}", initial_count)



        if initial_count == 0:

            logger.info("页面没有已上传的图片，无需清理")

            return 0



        max_iterations = initial_count + 10  # 最多删这么多轮，防止死循环

        cleared = 0

        idle_rounds = 0



# 减少空转轮数提升速度
        while cleared < max_iterations and idle_rounds < 1:

            # ── 先 hover 所有图片，触发删除按钮显示 ──

            # 优化：不是每轮都 hover，删除按钮 hover 一次后会保持显示
            # 只在第一轮（cleared == 0）和空转时 hover
            if cleared == 0 or idle_rounds > 0:
                await self._hover_all_images()

            await asyncio.sleep(0.3)  # 缩短hover等待提升速度



            # ── 多策略查找删除按钮 ──

            # 返回值说明：

            #   - Locator 对象：找到了 Playwright locator，需要调用 .click()

            #   - 字典 {"x":..., "y":...}：找到了坐标，已经用 mouse.click() 点击过了

            #   - None：没找到

            result = await self._find_delete_button()



            if result is None:

                idle_rounds += 1

                logger.info("本轮未找到删除按钮（第 {} 轮空转）", idle_rounds)

                # 空转时再 hover 一次，可能有些按钮没触发出来

                await self._hover_all_images()

                await asyncio.sleep(1)

                continue



            idle_rounds = 0



            try:

                # 判断返回值类型：

                # - 有 click 方法 → Playwright Locator

                # - 字典含 x, y → 坐标，需要用 mouse.click()

                # - None → 没找到（上面已经处理过）

                if hasattr(result, 'click'):

                    # 是 Playwright locator

                    try:

                        # 已注释掉滚动，避免删除时页面滚动

                        pass

                    except Exception:

                        pass



                    # 获取按钮信息用于日志

                    try:

                        tag = await result.evaluate("el => el.tagName")

                        aria = await result.get_attribute("aria-label") or ""

                        cls = (await result.get_attribute("class") or "")[:60]

                        logger.info("  点击删除按钮 (locator): tag={} aria={} class={}", tag, aria, cls)

                    except Exception:

                        logger.info("  点击删除按钮 (locator)")



                    await result.click(timeout=5000, force=False)

                    cleared += 1

                    logger.info("  ✓ 已点击删除按钮 #{}", cleared)

                elif isinstance(result, dict) and "x" in result and "y" in result:

                    # 是坐标字典，用 mouse.click()

                    x, y = result["x"], result["y"]

                    strategy = result.get("strategy", "unknown")

                    logger.info("  点击删除按钮 (坐标): 策略={} 位置=({},{})", strategy, int(x), int(y))



                    # 已注释掉滚动，避免删除时页面滚动

                    # 直接用坐标点击（假设已在可视区域）



                    await self.page.mouse.click(x, y)

                    cleared += 1

                    logger.info("  ✓ 已点击删除按钮 #{} (坐标点击)", cleared)

                else:

                    # 未知类型，当作没找到

                    idle_rounds += 1

                    logger.warning("  未知的返回值类型，跳过")

                    await asyncio.sleep(1)

                    continue



                # 等弹窗出现

                await asyncio.sleep(1)



                # 处理二次确认弹窗

                confirmed = await self._confirm_image_removal()

                if not confirmed:

                    logger.warning("  未检测到确认弹窗，可能无需确认或确认失败")



                # 等页面渲染，图片消失

                await asyncio.sleep(0.6)  # 缩短等待提升速度



                # 验证：检查图片数量是否减少

                # current_count = await self._count_uploaded_images()  # 已注释：提升速度，只在最后验证一次


                # logger.info("  删除后剩余图片数: {} (初始: {})", current_count, initial_count)  # 已注释：提升速度，只在最后验证一次




            except Exception as e:

                logger.warning("  点击删除按钮失败: {}", e)

                idle_rounds += 1

                await asyncio.sleep(1.5)



        # ── 最终验证 ──

        final_count = await self._count_uploaded_images()

        actual_cleared = initial_count - final_count



        if actual_cleared > 0:

            logger.info("清理完毕，实际删除 {} 张旧图片（剩余 {} 张）", actual_cleared, final_count)

        else:

            logger.warning("未能删除任何图片！初始 {} 张，最终 {} 张", initial_count, final_count)

            logger.warning("请查看 logs/screenshots 下的诊断文件分析页面结构")



        # 清理完成后滚动到页面底部，为后续上传做准备

        try:

            await self.page.evaluate("() => { window.scrollTo(0, document.body.scrollHeight); }")

        except Exception:

            pass

        await asyncio.sleep(1)





        # ★ 删除完成后验证页面是否还在管理图片页面

        # 防止删除最后一张图片后页面自动跳转

        try:

            current_url = self.page.url

            logger.info("删除完成后页面 URL: {}", current_url)



            # 检查是否还在管理图片页面

            if "manage-images" not in current_url and "image" not in current_url.lower():

                logger.warning("⚠️ 页面已跳转到其他页面！URL: {}", current_url)

                logger.warning("可能是删除最后一张图片后页面自动跳转了")

        except Exception as e:

            logger.debug("检查页面URL失败: {}", e)



        return actual_cleared



    async def _count_uploaded_images(self) -> int:

        """统计页面上已上传的图片数量。"""

        try:

            count = await self.page.evaluate(

                """() => {

                    // 多种方式统计已上传图片

                    const selectors = [

                        'img.uploaded-image',

                        'img[class*="uploaded"]',

                        '.imageArea img[src*="media-amazon"]',

                        '[class*="image-card"] img[src*="amazon"]',

                        'img[src*="m.media-amazon.com"]',

                    ];

                    const seen = new Set();

                    for (const sel of selectors) {

                        const imgs = document.querySelectorAll(sel);

                        for (const img of imgs) {

                            const r = img.getBoundingClientRect();

                            if (r.width > 30 && r.height > 30) {

                                seen.add(img.src);

                            }

                        }

                    }

                    return seen.size;

                }"""

            )

            return count

        except Exception as e:

            logger.warning("统计图片数量失败: {}", e)

            return 0



    async def _hover_all_images(self) -> None:

        """hover 到所有已上传图片上，触发删除按钮显示。



        亚马逊后台的删除按钮默认隐藏，鼠标悬停在图片上才会出现。

        """

        try:

            await self.page.evaluate(

                """() => {

                    // 找到所有已上传的图片

                    const imgSelectors = [

                        'img.uploaded-image',

                        'img[class*="uploaded"]',

                        '.imageArea img',

                        '[class*="image-card"] img',

                        'img[src*="m.media-amazon.com"]',

                    ];

                    const images = [];

                    const seen = new Set();

                    for (const sel of imgSelectors) {

                        const imgs = document.querySelectorAll(sel);

                        for (const img of imgs) {

                            const r = img.getBoundingClientRect();

                            if (r.width > 30 && r.height > 30 && !seen.has(img.src)) {

                                seen.add(img.src);

                                images.push(img);

                            }

                        }

                    }



                    // 对每张图片触发 mouseover 事件（模拟 hover）

                    for (const img of images) {

                        const events = ['mouseover', 'mouseenter', 'mousemove'];

                        for (const evt of events) {

                            try {

                                const rect = img.getBoundingClientRect();

                                const event = new MouseEvent(evt, {

                                    bubbles: true,

                                    cancelable: true,

                                    view: window,

                                    clientX: rect.left + rect.width / 2,

                                    clientY: rect.top + rect.height / 2,

                                });

                                img.dispatchEvent(event);

                                // 也向上冒泡到父元素

                                let p = img.parentElement;

                                for (let i = 0; i < 5 && p; i++) {

                                    p.dispatchEvent(event.cloneNode());

                                    p = p.parentElement;

                                }

                            } catch (e) { /* ignore */ }

                        }

                    }

                    return images.length;

                }"""

            )

        except Exception as e:

            logger.debug("hover 图片失败: {}", e)



    async def _find_delete_button(self):

        """查找删除按钮，返回 Playwright Locator 或 None。



        按优先级尝试多种策略（从最精确到最兜底）：

        1. 精确 aria-label 匹配（"清除图片"/"Delete image"/"Remove image"）

        2. 垃圾桶图标匹配（kat-icon delete_forever / delete / trash）

        3. 图片卡片底部工具栏最右侧的按钮（亚马逊后台实际布局）

        4. JS 精确查找：在图片卡片底部工具栏找最右边的按钮



        重要：删除按钮在图片卡片的底部工具栏最右侧，不是右上角！

        """

        # ── 策略 1: 精确 aria-label 匹配 ──

        aria_selectors = [

            'button[aria-label="清除图片"]',

            'button[aria-label="Delete image"]',

            'button[aria-label="delete image"]',

            'button[aria-label="Remove image"]',

            'button[aria-label="remove image"]',

            'button[aria-label="删除图片"]',

            '[role="button"][aria-label="清除图片"]',

            '[role="button"][aria-label="Delete image"]',

            '[role="button"][aria-label="删除图片"]',

        ]

        for sel in aria_selectors:

            try:

                loc = self.page.locator(sel).first

                if await loc.count() > 0 and await loc.is_visible():

                    # 验证：确保在图片卡片内

                    in_image_card = await loc.evaluate(

                        """btn => {

                            let p = btn;

                            for (let i = 0; i < 10 && p; i++) {

                                const cls = (p.className || '').toString();

                                if (cls.includes('imageArea') || cls.includes('image-card') ||

                                    cls.includes('image-tile') || cls.includes('image-container')) {

                                    return true;

                                }

                                p = p.parentElement;

                            }

                            return false;

                        }"""

                    )

                    if in_image_card:

                        logger.info("找到删除按钮（策略1: aria-label精确匹配）: {}", sel)

                        return loc

                    else:

                        logger.warning("找到aria-label匹配的按钮但不在图片卡片内，跳过")

            except Exception:

                continue



        # ── 策略 2: 垃圾桶图标匹配（最可靠） ──

        try:

            icon_selectors = [

                'kat-icon[name="delete_forever"]',

                'kat-icon[name="delete"]',

                'kat-icon[name="trash"]',

                '[icon="delete_forever"]',

                '[icon="delete"]',

                '[icon="trash"]',

                '.delete-icon',

                '.trash-icon',

            ]

            for sel in icon_selectors:

                locs = self.page.locator(sel)

                cnt = await locs.count()

                for i in range(cnt):

                    loc = locs.nth(i)

                    try:

                        if not await loc.is_visible():

                            continue

                    except Exception:

                        continue



                    # 找到它的父按钮元素

                    parent_btn = await loc.evaluate_handle(

                        """el => {

                            let p = el;

                            for (let i = 0; i < 6 && p; i++) {

                                if (p.tagName === 'BUTTON' || p.getAttribute('role') === 'button') return p;

                                p = p.parentElement;

                            }

                            return null;

                        }"""

                    )

                    parent_el = parent_btn.as_element()

                    if not parent_el:

                        continue



                    # 验证：父按钮必须在图片卡片内

                    in_image_card = await parent_el.evaluate(

                        """btn => {

                            let p = btn;

                            for (let i = 0; i < 10 && p; i++) {

                                const cls = (p.className || '').toString();

                                if (cls.includes('imageArea') || cls.includes('image-card') ||

                                    cls.includes('image-tile') || cls.includes('image-container')) {

                                    return true;

                                }

                                p = p.parentElement;

                            }

                            return false;

                        }"""

                    )

                    if in_image_card:

                        logger.info("找到删除按钮（策略2: 垃圾桶图标）")

                        return parent_el

        except Exception as e:

            logger.debug("策略2查找异常: {}", e)



        # ── 策略 3: 图片卡片底部工具栏最右侧按钮 ──

        try:

            # 用 JS 精确找：在每个图片卡片的底部工具栏中找最右边的按钮

            btn_info = await self.page.evaluate(

                """() => {

                    // 1. 找到所有图片卡片（包含已上传图片的容器）

                    const imageCards = [];

                    const imgs = document.querySelectorAll('img.uploaded-image, img[class*="uploaded"], img[src*="m.media-amazon.com"]');

                    const seenCards = new Set();



                    for (const img of imgs) {

                        const r = img.getBoundingClientRect();

                        if (r.width < 50 || r.height < 50) continue;



                        // 向上找图片卡片容器（包含图片和底部工具栏）

                        let card = null;

                        let p = img.parentElement;

                        for (let i = 0; i < 10 && p; i++) {

                            const cls = (p.className || '').toString();

                            // 特征：有 imageArea / image-card 等类名，或者包含图片+底部按钮栏

                            const hasImage = p.querySelectorAll('img').length > 0;

                            const hasButtons = p.querySelectorAll('button').length >= 3;

                            if ((cls.includes('imageArea') || cls.includes('image-card') ||

                                 cls.includes('image-tile') || cls.includes('image-container')) &&

                                hasImage && hasButtons) {

                                card = p;

                                break;

                            }

                            // 兜底：找包含图片且有多个按钮的 div

                            if (p.tagName === 'DIV' && hasImage && hasButtons &&

                                p.querySelectorAll('button').length >= 3 && p.querySelectorAll('img').length <= 2) {

                                card = p;

                                break;

                            }

                            p = p.parentElement;

                        }



                        if (card && !seenCards.has(card)) {

                            seenCards.add(card);

                            imageCards.push(card);

                        }

                    }



                    if (imageCards.length === 0) return null;



                    // 2. 在第一个图片卡片中找底部工具栏最右边的按钮（删除按钮）

                    const card = imageCards[0];

                    const cardRect = card.getBoundingClientRect();



                    // 找卡片内所有按钮

                    const allBtns = card.querySelectorAll('button, [role="button"], kat-icon-button');

                    const visibleBtns = [];



                    for (const btn of allBtns) {

                        const r = btn.getBoundingClientRect();

                        if (r.width <= 0 || r.height <= 0) continue;

                        const s = window.getComputedStyle(btn);

                        if (s.display === 'none' || s.visibility === 'hidden' || s.opacity === '0') continue;



                        // 按钮应该在卡片的下半部分（底部工具栏）

                        const btnCenterY = r.top + r.height / 2;

                        const cardBottom = cardRect.bottom;

                        const inBottomArea = btnCenterY > cardRect.top + cardRect.height * 0.6;



                        if (!inBottomArea) continue;



                        visibleBtns.push({

                            btn: btn,

                            x: r.left + r.width / 2,

                            y: r.top + r.height / 2,

                            right: r.right,

                            width: r.width,

                            height: r.height,

                            aria: btn.getAttribute('aria-label') || '',

                            title: btn.getAttribute('title') || '',

                            cls: (btn.className || '').toString(),

                        });

                    }



                    if (visibleBtns.length === 0) return null;



                    // 3. 按 x 坐标从左到右排序，最右边的就是删除按钮

                    visibleBtns.sort((a, b) => a.x - b.x);

                    const rightmost = visibleBtns[visibleBtns.length - 1];



                    // 验证：最右边的按钮应该有删除相关特征（垃圾桶图标、delete类名等）

                    const hasDeleteFeature =

                        /delete|remove|trash|清除|删除/i.test(rightmost.aria) ||

                        /delete|remove|trash/i.test(rightmost.title) ||

                        /delete|remove|trash/i.test(rightmost.cls) ||

                        rightmost.btn.querySelector('kat-icon[name*="delete"]') ||

                        rightmost.btn.querySelector('kat-icon[name*="trash"]') ||

                        rightmost.btn.querySelector('[icon*="delete"]') ||

                        rightmost.btn.querySelector('[icon*="trash"]');



                    if (hasDeleteFeature || visibleBtns.length >= 3) {

                        // 如果有删除特征，或者至少有3个按钮（左移/右移/添加/删除），最右边的就是删除

                        return {

                            x: rightmost.x,

                            y: rightmost.y,

                            tag: rightmost.btn.tagName,

                            aria: rightmost.aria,

                            cls: rightmost.cls.substring(0, 100),

                            btnIndex: visibleBtns.length,

                            hasDeleteFeature: hasDeleteFeature,

                            strategy: 'bottom_right',

                        };

                    }



                    return null;

                }"""

            )



            if btn_info:

                logger.info("找到删除按钮（策略3: 图片卡片底部最右侧）: tag={} aria={} 按钮数={} 有删除特征={}",

                            btn_info["tag"], btn_info["aria"],

                            btn_info["btnIndex"], btn_info["hasDeleteFeature"])

                return btn_info

        except Exception as e:

            logger.debug("策略3查找异常: {}", e)



        # ── 策略 4: 兜底 - 找所有含 delete/trash 且在图片区域内的按钮 ──

        try:

            btn_info = await self.page.evaluate(

                """() => {

                    const allBtns = document.querySelectorAll('button, [role="button"]');

                    const candidates = [];



                    for (const btn of allBtns) {

                        const r = btn.getBoundingClientRect();

                        if (r.width <= 0 || r.height <= 0) continue;

                        const s = window.getComputedStyle(btn);

                        if (s.display === 'none' || s.visibility === 'hidden' || s.opacity === '0') continue;



                        // 必须在图片卡片内

                        let inImageCard = false;

                        let p = btn;

                        for (let i = 0; i < 10 && p; i++) {

                            const cls = (p.className || '').toString();

                            if (cls.includes('imageArea') || cls.includes('image-card') ||

                                cls.includes('image-tile') || cls.includes('image-container')) {

                                inImageCard = true;

                                break;

                            }

                            p = p.parentElement;

                        }

                        if (!inImageCard) continue;



                        // 检查是否有删除相关特征

                        const aria = (btn.getAttribute('aria-label') || '').toLowerCase();

                        const title = (btn.getAttribute('title') || '').toLowerCase();

                        const cls = (btn.className || '').toString().toLowerCase();

                        const hasDeleteIcon = btn.querySelector('kat-icon[name*="delete"]') ||

                                              btn.querySelector('kat-icon[name*="trash"]') ||

                                              btn.querySelector('[icon*="delete"]') ||

                                              btn.querySelector('[icon*="trash"]');



                        const isDelete = /delete|remove|trash|清除|删除/.test(aria) ||

                                        /delete|remove|trash|清除|删除/.test(title) ||

                                        /delete|remove|trash/.test(cls) ||

                                        hasDeleteIcon;



                        if (isDelete) {

                            candidates.push({

                                btn: btn,

                                x: r.left + r.width / 2,

                                y: r.top + r.height / 2,

                                aria: aria,

                            });

                        }

                    }



                    if (candidates.length > 0) {

                        const c = candidates[0];

                        return {

                            x: c.x,

                            y: c.y,

                            tag: c.btn.tagName,

                            aria: c.aria,

                            strategy: 'fallback_keyword',

                        };

                    }

                    return null;

                }"""

            )



            if btn_info:

                logger.info("找到删除按钮（策略4: 兜底-图片区域内删除关键词）: tag={} aria={}",

                            btn_info["tag"], btn_info["aria"])

                return btn_info

        except Exception as e:

            logger.debug("策略4查找异常: {}", e)



        return None



    async def _confirm_image_removal(self) -> bool:

        """处理删除图片后可能弹出的二次确认对话框（『确定删除？』）。



        改进版：只在弹窗容器内部查找确认按钮，避免误点页面上的其他按钮。



        Returns:

            True 表示确认成功或无需确认，False 表示确认失败

        """
        # ⚡ 快速确认：直接按 Enter 键（删除确认通常 Enter 就可以）
        try:
            await asyncio.sleep(0.3)  # 等一下让弹窗出现
            await self.page.keyboard.press("Enter")
            await asyncio.sleep(0.4)
            logger.debug("⚡ 快速确认：已按 Enter")
            return True
        except Exception:
            pass


        # 弹窗容器选择器

        popup_selectors = [

            '[role="dialog"]',

            '[class*="modal" i]',

            '[class*="dialog" i]',

            '[class*="confirm" i]',

            '[class*="popover" i]',

            '[class*="popup" i]',

            'kat-modal',

            'kat-dialog',

            'kat-popover',

        ]



        confirm_texts = [

            "Delete", "删除", "Remove", "移除",

            "确定", "确认", "Yes", "OK", "Confirm",

            "Delete image", "删除图片", "Remove image",

        ]



        # 轮询等待弹窗出现（最多等 3 秒）

        popup_locator = None

        for _ in range(6):

            for sel in popup_selectors:

                try:

                    loc = self.page.locator(sel).first

                    if await loc.count() > 0 and await loc.is_visible():

                        popup_locator = loc

                        break

                except Exception:

                    continue

            if popup_locator is not None:

                break

            await asyncio.sleep(0.5)



        if popup_locator is None:

            # 没有弹窗，可能不需要确认

            return True



        logger.info("  检测到删除确认弹窗，尝试点击确认按钮...")



        # ★ 只在弹窗内部查找确认按钮，避免误点页面其他按钮

        for text in confirm_texts:

            for sel in [

                f'button:has-text("{text}")',

                f'[role="button"]:has-text("{text}")',

                f'kat-button:has-text("{text}")',

                f'a:has-text("{text}")',

            ]:

                try:

                    # 在弹窗容器内查找，而不是整个页面

                    loc = popup_locator.locator(sel).first

                    if await loc.count() > 0 and await loc.is_visible():

                        await loc.click(timeout=3000)

                        logger.info("  ✓ 已确认删除弹窗（点击: {}）", text)

                        await asyncio.sleep(1)

                        return True

                except Exception:

                    continue



        # 策略2：在弹窗内查找所有按钮，点击最后一个（确认按钮通常在最后）

        try:

            btns = popup_locator.locator('button, kat-button, [role="button"], a')

            cnt = await btns.count()

            if cnt > 0:

                logger.info("  弹窗内找到 {} 个按钮，尝试点击最后一个", cnt)

                for j in range(cnt - 1, -1, -1):

                    btn = btns.nth(j)

                    try:

                        if await btn.is_visible() and await btn.is_enabled():

                            await btn.click(timeout=3000)

                            logger.info("  ✓ 点击弹窗内第 {} 个按钮（从后往前）", j + 1)

                            await asyncio.sleep(1)

                            return True

                    except Exception:

                        continue

        except Exception as e:

            logger.debug("  弹窗内按钮查找失败: {}", e)



        # 兜底：按 Enter 键

        try:

            await self.page.keyboard.press("Enter")

            logger.info("  ✓ 按 Enter 确认删除弹窗（兜底）")

            await asyncio.sleep(1)

            return True

        except Exception as e:

            logger.warning("  确认弹窗失败: {}", e)

            return False



    async def search_sku(self, sku: str) -> bool:

        """在库存页搜索 SKU，返回是否搜到。

        优化：用智能等待替代固定 sleep，减少无效等待。
        """

        logger.info("搜索 SKU: {}", sku)

        # 智能等待：等搜索框出现，替代固定 sleep(2)
        search_box_selectors = [
            'input[placeholder="搜索 SKU、商品名称/关键词、FNSKU、ASIN、UPC/EAN"]',
            'input[placeholder*="搜索 SKU、商品名称/关键词"]',
            'input[placeholder*="FNSKU、ASIN、UPC/EAN"]',
            'input[placeholder*="SKU、商品名称/关键词"]',
            'input[placeholder*="搜索 SKU"]',
            "#inventory-search-filter",
            'input[type="search"]',
            'input[name*="search"]',
        ]

        box = None
        for sel in search_box_selectors:
            try:
                loc = self.page.locator(sel).first
                await loc.wait_for(state="visible", timeout=3000)
                box = loc
                logger.info("使用搜索框: {}", sel)
                break
            except Exception:
                continue

        if box is None:
            # 最后兜底：模糊匹配
            try:
                loc = self.page.locator('input[type="text"][placeholder]').first
                await loc.wait_for(state="visible", timeout=3000)
                box = loc
                logger.info("使用兜底搜索框")
            except Exception:
                logger.error("找不到搜索框")
                await self._diagnose("搜索SKU失败_无搜索框")
                return False

        try:
            await box.fill("")
            await box.fill(sku)

            # 输入后随机等待1-2秒，再按回车搜索
            wait_after_input = random.uniform(1, 2)
            logger.info(f"已输入SKU，随机等待 {wait_after_input:.1f}秒后搜索...")
            await asyncio.sleep(wait_after_input)

            await box.press("Enter")
        except Exception as e:
            logger.error("填写搜索框失败: {}", e)
            await self._diagnose("搜索SKU失败_填框异常")
            return False

        # 智能等待：等搜索结果出现，替代固定 sleep(3)
        try:
            await self.page.wait_for_function(
                """(sku) => {
                    const rows = document.querySelectorAll('.inventory-row, tr, [role="row"], [data-testid*="inventory"] tbody tr');
                    for (const row of rows) {
                        if (row.innerText && row.innerText.includes(sku)) return true;
                    }
                    return false;
                }""",
                arg=sku,
                timeout=10000,
            )
            logger.info("✅ 搜索成功，找到 SKU: {}", sku)
            return True
        except Exception:
            # 超时后再检查一次 body 文本
            body_text = await self.page.locator("body").inner_text()
            found = sku in body_text
            if not found:
                logger.warning("搜索结果中未找到 SKU: {}", sku)
                await self._diagnose("搜索SKU失败_无结果")
            return found



    async def _find_row_by_sku_js(self, sku: str) -> Any | None:

        """用 JS 从 SKU 文本节点向上遍历，找到真正的商品行元素。"""

        try:

            handle = await self.page.evaluate_handle(

                """(sku) => {

                    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null, false);

                    let node;

                    while (node = walker.nextNode()) {

                        if (node.textContent.includes(sku)) {

                            let el = node.parentElement;

                            while (el && el !== document.body) {

                                const tag = el.tagName.toLowerCase();

                                const role = el.getAttribute('role');

                                if (tag === 'tr' || role === 'row' || el.classList.contains('inventory-row')) {

                                    return el;

                                }

                                // 如果父元素是 div 且包含操作按钮（含亚马逊自定义 kat-dropdown-button），也视为行容器

                                if (tag === 'div' && el.querySelectorAll('button, [role="button"], kat-dropdown-button, [class*="action"]').length > 0) {

                                    // 进一步确认：该 div 内部包含价格符号或货币文本

                                    if (/[€£$¥]|EUR|GBP|USD|价格|Price/i.test(el.innerText)) {

                                        return el;

                                    }

                                }

                                el = el.parentElement;

                            }

                        }

                    }

                    return null;

                }""",

                sku,

            )

            element = handle.as_element()

            if element:

                logger.info("通过 JS 定位到 SKU 行")

                return element

        except Exception as e:

            logger.warning("JS 定位 SKU 行失败: {}", e)

        return None



    async def _find_first_result_row(self, sku: str) -> Any | None:

        """尝试多种方式定位搜索结果中的商品行。"""

        # 1. 最优先：用 JS 从 SKU 文本节点向上找真实行

        row = await self._find_row_by_sku_js(sku)

        if row is not None:

            return row



        # 2. CSS 方式：行内包含 SKU 文本（但避免过宽的 div）

        for sel in [

            f'tr:has-text("{sku}")',

            f'[role="row"]:has-text("{sku}")',

            f'.inventory-row:has-text("{sku}")',

            f'[data-testid*="row"]:has-text("{sku}")',

        ]:

            try:

                loc = self.page.locator(sel).first

                if await loc.count() > 0 and await loc.is_visible():

                    logger.info("定位到 SKU 行: {}", sel)

                    return loc

            except Exception:

                continue



        # 3. 兜底：直接取搜索结果表格的第一条数据行

        for sel in [

            'table tbody tr',

            '.inventory-table tbody tr',

            '[data-testid*="inventory"] tbody tr',

            '[data-testid*="table"] tbody tr',

            'tbody tr',

        ]:

            try:

                loc = self.page.locator(sel).first

                if await loc.count() > 0 and await loc.is_visible():

                    logger.info("使用表格第一行: {}", sel)

                    return loc

            except Exception:

                continue



        # 4. 再兜底：找页面中任何包含操作菜单按钮的可见行

        for sel in [

            '[role="row"]',

            'tr',

            '.inventory-row',

            '[data-testid*="row"]',

        ]:

            try:

                locs = self.page.locator(sel)

                cnt = await locs.count()

                for i in range(cnt):

                    r = locs.nth(i)

                    if not await r.is_visible():

                        continue

                    if await r.locator("button, [role='button']").count() > 0:

                        logger.info("使用含按钮的可见行: {} index={}", sel, i)

                        return r

            except Exception:

                continue

        return None



    async def open_manage_images(self, sku: str) -> bool:

        """点击商品行右侧三个点菜单 → 管理图片。

        优化：用智能等待替代固定 sleep——等按钮可见、等菜单弹出、等新标签页出现。
        """

        logger.info("打开管理图片: {}", sku)

        try:

            url_before = self.page.url

            # 1. 智能等待三个点按钮出现（替代固定 sleep(2)）
            dots = self.page.locator('kat-dropdown-button[single-target-icon="vertical-dots"]')
            try:
                await dots.first.wait_for(state="visible", timeout=8000)
            except Exception:
                logger.warning("等待三个点按钮超时，继续尝试")

            cnt = await dots.count()

            logger.info("找到 {} 个 kat-dropdown-button(vertical-dots)", cnt)

            clicked = False

            for i in range(cnt):

                btn = dots.nth(i)

                if not await btn.is_visible():

                    continue

                box = await btn.bounding_box()

                if not box or box["width"] == 0:

                    continue

                logger.info(

                    "点击三个点按钮 #{} at ({},{}) {}x{}",

                    i, int(box["x"]), int(box["y"]), int(box["width"]), int(box["height"]),

                )

                await btn.click()

                clicked = True

                break

            if not clicked:

                logger.error("未找到三个点按钮，导出诊断文件")

                await self._diagnose("打开管理图片失败_无三个点按钮")

                await self._dump_html(sku)

                return False

            # 2. 智能等待菜单弹出（替代固定 sleep(1.5)）
            menu_texts = ["管理图片", "Manage Images", "Manage images", "Edit images", "Edit Images"]

            menu_clicked = False

            # 记录点击前的标签页，用于检测新标签页

            pages_before = set(self._context.pages) if self._context else set()

            # 等菜单项出现，最多等 5 秒，每 0.3 秒检查一次
            menu_found = False
            for _ in range(17):  # 17 * 0.3 ≈ 5秒
                for text in menu_texts:
                    try:
                        loc = self.page.get_by_text(text, exact=False).first
                        if await loc.count() > 0 and await loc.is_visible():
                            menu_found = True
                            break
                    except Exception:
                        pass
                if menu_found:
                    break
                await asyncio.sleep(0.3)

            if not menu_found:
                logger.warning("菜单未及时弹出，继续尝试查找")

            # 随机等待1-3秒，避免操作过快被风控
            wait_before_click = random.uniform(1, 3)
            logger.info(f"菜单已弹出，随机等待 {wait_before_click:.1f}秒后点击管理图片...")
            await asyncio.sleep(wait_before_click)

            for text in menu_texts:

                # 方式1: Playwright get_by_text（最可靠，匹配任何标签）
                try:

                    loc = self.page.get_by_text(text, exact=False).first

                    if await loc.count() > 0 and await loc.is_visible():

                        await loc.click(timeout=3000)

                        logger.info("✅ 点击菜单项: {}", text)

                        menu_clicked = True

                        break

                except Exception:

                    pass

                # 方式2: CSS 选择器匹配各种可能的菜单项标签
                for sel in [

                    f'kat-dropdown-item:has-text("{text}")',

                    f'a:has-text("{text}")',

                    f'button:has-text("{text}")',

                    f'[role="menuitem"]:has-text("{text}")',

                    f'[role="menuitemradio"]:has-text("{text}")',

                    f'div:has-text("{text}")',

                    f'span:has-text("{text}")',

                    f'li:has-text("{text}")',

                ]:

                    try:

                        loc = self.page.locator(sel).first

                        if await loc.count() > 0 and await loc.is_visible():

                            await loc.click(timeout=3000)

                            logger.info("✅ 点击菜单项: {} (selector={})", text, sel)

                            menu_clicked = True

                            break

                    except Exception:

                        continue
                if menu_clicked:

                    # 点击后随机等待1-2秒，再等新标签页
                    wait_after_click = random.uniform(1, 2)
                    logger.info(f"已点击管理图片，随机等待 {wait_after_click:.1f}秒...")
                    await asyncio.sleep(wait_after_click)

                    break

            if not menu_clicked:

                # 导出菜单弹出后的 HTML，看菜单项到底是什么标签

                logger.error("未找到「管理图片」菜单项，导出菜单弹出后的 HTML")

                await self._diagnose("打开管理图片失败_无菜单项")

                await self._dump_html(sku)

                return False

            # 3. 智能等待新标签页出现（替代固定 sleep(2)）
            new_page = None
            for _ in range(20):  # 20 * 0.25 = 5秒
                pages_after = set(self._context.pages) if self._context else set()
                new_pages = pages_after - pages_before
                if new_pages:
                    new_page = new_pages.pop()
                    break
                await asyncio.sleep(0.25)

            if new_page:

                # 切换到新标签页

                logger.info("检测到新标签页打开，切换到管理图片标签页: {}", new_page.url)

                await new_page.wait_for_load_state("domcontentloaded", timeout=20000)

                self._orig_page = self._page

                self._page = new_page

                logger.info("✅ 已切换到管理图片标签页")

            else:

                # 没有新标签页，检查当前页是否已导航到管理图片页面

                logger.info("未检测到新标签页，当前页 URL: {}", self.page.url)

            # 4. 验证：URL 不应该跳到"添加商品/批量上传"页面

            url_after = self.page.url

            if "uploadInventory" in url_after or "addproduct" in url_after.lower():

                logger.error("点击后跳转到了错误页面（添加商品）: {}", url_after)

                await self._diagnose("打开管理图片失败_跳转到添加商品")

                await self._dump_html(sku)

                return False

            return True

        except Exception as e:

            logger.error("打开管理图片异常: {}", e)

            await self._diagnose(f"打开管理图片异常_{sku}")

            await self._dump_html(sku)

            return False



    async def upload_images(self, image_paths: list[str]) -> bool:

        """依次上传全部图片。



        改进版：

        1. 优先使用 set_input_files 直接上传，不弹出系统文件选择框

        2. 直接滚动到页面底部，不反复翻页

        3. 上传完成后等待图片验证完成

        """

        logger.info("开始上传 {} 张图片", len(image_paths))

        logger.info("当前标签页 URL: {}", self.page.url)



        # 等待管理图片页面加载完成（新标签页需要更充分的加载时间）

        logger.info("等待管理图片页面加载...")

        try:

            await self.page.wait_for_load_state("networkidle", timeout=20000)

        except Exception:

            logger.warning("页面 networkidle 超时，继续尝试")

        await asyncio.sleep(3)



        # 记录当前 URL，用于后续验证是否在正确的管理图片页面

        cur_url = self.page.url

        logger.info("管理图片页面 URL: {}", cur_url)



        # 上传新图片前，先清空页面上已有的旧图片占位卡（开关控制）

        upload_cfg = self.cfg.get("upload", {}) or {}

        if upload_cfg.get("clear_existing_images", True):

            await self.clear_image_widgets()

        else:

            logger.info("upload.clear_existing_images=false，跳过清理步骤")



        # 清理后/上传前再导出一次页面信息（诊断用）

        # 已注释掉上传前的页面导出，提升速度
        # await self._dump_manage_images_page_info("上传前")



        # ★ 直接滚动到页面底部，所有操作都在底部完成，不反复翻页

        logger.info("滚动到页面底部...")

        try:

            await self.page.evaluate("() => { window.scrollTo(0, document.body.scrollHeight); }")

            await asyncio.sleep(1)

        except Exception:

            pass



        uploaded = 0

        for idx, img in enumerate(image_paths):

            if not os.path.exists(img):

                logger.warning("图片不存在，跳过: {}", img)

                continue

            try:

                # ★ 策略1：优先用 input[type="file"] 直接上传（无弹窗）

                upload_success = False

                try:

                    file_inputs = self.page.locator('input[type="file"]')

                    count = await file_inputs.count()

                    if count > 0:

                        logger.info("找到 {} 个 file input，尝试直接上传", count)

                        # 尝试每个 file input，找到能用的那个

                        for fi_idx in range(min(count, 3)):  # 最多试前3个

                            try:

                                fi = file_inputs.nth(fi_idx)

                                # 用 set_input_files 上传（Playwright 官方推荐方式）

                                await fi.set_input_files(img)

                                upload_success = True

                                logger.info("✓ set_input_files 上传成功 (第{}个input): {}", fi_idx + 1, os.path.basename(img))

                                break

                            except Exception as e:

                                logger.debug("第{}个 file input 失败: {}", fi_idx + 1, e)

                                continue



                        # 如果 set_input_files 都失败，尝试用 evaluate 直接设置

                        if not upload_success:

                            logger.info("set_input_files 都失败，尝试 JS evaluate 方式...")

                            try:

                                # 用 JS 方式创建 DataTransfer 并设置文件

                                await self.page.evaluate(

                                    """(imgPath) => {

                                        const input = document.querySelector('input[type="file"]');

                                        if (input) {

                                            // 触发 change 事件模拟文件选择

                                            input.style.display = 'block';

                                            input.style.opacity = '1';

                                            input.style.visibility = 'visible';

                                        }

                                    }""",

                                    img

                                )

                                # 然后再试一次 set_input_files

                                await file_inputs.first.set_input_files(img)

                                upload_success = True

                                logger.info("✓ JS + set_input_files 方式成功: {}", os.path.basename(img))

                            except Exception as e2:

                                logger.debug("JS evaluate 方式也失败: {}", e2)

                except Exception as e:

                    logger.warning("set_input_files 方式失败: {}", e)



                # ★ 策略2：如果直接上传失败，尝试点击上传占位卡片 + filechooser

                if not upload_success:

                    logger.info("尝试点击上传占位卡片方式上传...")

                    slot_pos = await self._find_upload_slot()



                    if slot_pos:

                        try:

                            async with self.page.expect_file_chooser(timeout=10000) as fc_info:

                                await self.page.mouse.click(slot_pos["x"], slot_pos["y"])

                            fc = await fc_info.value

                            await fc.set_files(img)

                            upload_success = True

                            logger.info("✓ filechooser 方式上传成功: {}", os.path.basename(img))

                        except Exception as e:

                            logger.warning("filechooser 方式失败: {}", e)



                # ★ 策略3：兜底 - 点击通用上传按钮

                if not upload_success:

                    logger.warning("前两种方式都失败，尝试通用上传按钮...")

                    try:

                        async with self.page.expect_file_chooser(timeout=10000) as fc_info:

                            ok = await self._click_text(["Upload", "上传", "Add images", "添加图片", "Browse", "选择文件", "Add photo", "Upload from computer", "从计算机上传"])

                            if not ok:

                                raise RuntimeError("未找到通用上传按钮")

                        fc = await fc_info.value

                        await fc.set_files(img)

                        upload_success = True

                        logger.info("✓ 通用上传按钮方式成功: {}", os.path.basename(img))

                    except Exception as e:

                        logger.error("所有上传方式都失败: {}", e)

                        await self._diagnose(f"上传图片失败_{os.path.basename(img)}")

                        await self._dump_html(f"upload_fail_{os.path.basename(img)}")

                        return False



                logger.info("已上传 ({}/{}): {}", idx + 1, len(image_paths), os.path.basename(img))

                uploaded += 1

                # 随机等待1-5秒，等待图片上传并渲染，避免操作过快
                wait_after_upload = random.uniform(1, 5)
                logger.info(f"图片上传后随机等待 {wait_after_upload:.1f}秒...")
                await asyncio.sleep(wait_after_upload)

            except Exception as e:  # noqa: BLE001

                logger.error("上传失败 {}: {}", os.path.basename(img), e)

                await self._diagnose(f"上传图片失败_{os.path.basename(img)}")



        logger.info("上传完成，成功 {} / {}", uploaded, len(image_paths))



        # ★ 上传完成后，等待图片验证（按钮从"正在验证"变成"保存并完成"）

        if uploaded > 0:

            logger.info("等待图片验证完成...")

            await self._wait_for_save_button_ready()



        return uploaded > 0



    async def _find_upload_slot(self):

        """找到图片网格中真正的"上传"占位卡片（正方形，相机图标 + "上传"文字）。



        排除：

        - 已有 uploaded-image 的卡片（那是已有图片，不是上传占位）

        - 批量上传表格组件（spreadsheet-uploader / kat-file-upload）



        返回 {"x": int, "y": int} 或 None。

        """

        try:

            candidates = await self.page.evaluate(

                """() => {

                    const results = [];

                    const isInBulkUploader = (el) => {

                        let p = el;

                        while (p && p !== document.body) {

                            const cls = (p.className || '').toString();

                            if (cls.includes('spreadsheet-uploader') || cls.includes('bulk') || cls.includes('file-upload')) return true;

                            p = p.parentElement;

                        }

                        return false;

                    };



                    const all = document.querySelectorAll('div, span, button, a, kat-card, [role="button"]');

                    for (const el of all) {

                        const rect = el.getBoundingClientRect();

                        if (rect.width < 50 || rect.height < 50) continue;

                        if (rect.width > 300 || rect.height > 300) continue;

                        const ratio = rect.width / rect.height;

                        if (ratio < 0.7 || ratio > 1.4) continue;

                        const style = window.getComputedStyle(el);

                        if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') continue;

                        if (isInBulkUploader(el)) continue;



                        // ★ 关键排除：跳过含 uploaded-image 的卡片（那是已有图片）

                        if (el.querySelector('img.uploaded-image, img[class*="uploaded"], img[src*="media-amazon"]')) continue;



                        const text = (el.innerText || '').trim();

                        const hasUploadText = text === '上传' || text.toLowerCase() === 'upload' ||

                                               text.includes('上传') || text.toLowerCase().includes('upload');

                        // 更精确的相机图标判断（排除太宽泛的 image class）

                        const hasCameraIcon = !!el.querySelector(

                            'svg[class*="camera" i], svg[class*="Camera"], [class*="camera" i], ' +

                            'svg[class*="upload" i], [class*="upload-icon" i], [class*="placeholder" i]'

                        );



                        if (hasUploadText || hasCameraIcon) {

                            results.push({

                                x: Math.round(rect.x),

                                y: Math.round(rect.y),

                                w: Math.round(rect.width),

                                h: Math.round(rect.height),

                                ratio: ratio.toFixed(2),

                                text: text.substring(0, 30),

                                hasUploadText: hasUploadText,

                                hasCameraIcon: hasCameraIcon,

                                html: el.outerHTML.substring(0, 300)

                            });

                        }

                    }

                    results.sort((a, b) => a.y - b.y || a.x - b.x);

                    return results.slice(0, 5);

                }"""

            )



            if not candidates:

                logger.warning("未找到空的上传占位卡片（可能所有图位都已有图片，或页面结构不同）")

                return None



            logger.info("找到 {} 个空上传占位候选", len(candidates))

            for c in candidates:

                logger.info("  上传候选: ({},{}) {}x{} ratio={} text='{}' hasUploadText={} hasCameraIcon={} html={}",

                            c["x"], c["y"], c["w"], c["h"], c["ratio"],

                            c["text"], c["hasUploadText"], c["hasCameraIcon"],

                            c["html"][:120])



            target = candidates[0]

            x, y = target["x"] + target["w"] / 2, target["y"] + target["h"] / 2



            # # 滚动到可见区域  # 已注释：已滚到底部，无需再滚动            # await self.page.evaluate("([x, y]) => { window.scrollTo(x - 200, y - 200); }", [int(x), int(y)])  # 已注释：已滚到底部，无需再滚动            await asyncio.sleep(0.5)



            logger.info("准备点击上传占位卡片中心: ({}, {})", int(x), int(y))

            return {"x": int(x), "y": int(y)}

        except Exception as e:

            logger.warning("查找上传占位卡片异常: {}", e)

            return None



    async def save_and_complete(self) -> bool:

        """点击「保存并完成」，等待弹出框并点击「确定」。"""

        logger.info("=== 保存并完成 ===")



        # 先滚动到页面底部（保存按钮在右下角）

        try:

            await self.page.evaluate("() => { window.scrollTo(0, document.body.scrollHeight); }")

            await asyncio.sleep(0.8)

        except Exception:

            pass





        # ★ 等待保存按钮就绪（从"正在验证"变成"保存并完成"）

        await self._wait_for_save_button_ready()



        # 多策略查找保存按钮

        saved = False



        # 策略1: 用 _click_text 点击（已增加 kat-button 支持）

        save_texts = [

            "保存并完成", "Save and finish", "Save and Finish",

            "Save and complete", "Save & finish", "Save & Finish",

            "保存", "Save", "Submit", "Done", "完成",

        ]

        ok = await self._click_text(save_texts, timeout=5000)

        if ok:

            saved = True

            logger.info("✓ 已点击保存按钮（策略1: 文本匹配）")



        # 策略2: 直接用 JS 找右下角的按钮（保存按钮通常在右下角）

        if not saved:

            logger.info("策略1未找到保存按钮，尝试策略2: JS查找右下角按钮...")

            try:

                btn_info = await self.page.evaluate(

                    """() => {

                        const allBtns = document.querySelectorAll('button, kat-button, [role="button"], a');

                        const candidates = [];

                        const saveKeywords = ['保存并完成', 'Save and finish', 'Save and complete', '保存', 'Save', 'Submit', 'Done'];



                        for (const btn of allBtns) {

                            const r = btn.getBoundingClientRect();

                            if (r.width <= 0 || r.height <= 0) continue;

                            const s = window.getComputedStyle(btn);

                            if (s.display === 'none' || s.visibility === 'hidden' || s.opacity === '0') continue;



                            const text = (btn.innerText || btn.textContent || '').trim();

                            const isSaveBtn = saveKeywords.some(kw => text.includes(kw) || text.toLowerCase().includes(kw.toLowerCase()));



                            if (isSaveBtn) {

                                // 优先选右下角的按钮

                                const score = r.top + r.left * 0.1; // 越靠下越靠右，分数越高

                                candidates.push({

                                    btn: btn,

                                    x: r.left + r.width / 2,

                                    y: r.top + r.height / 2,

                                    text: text.substring(0, 30),

                                    score: score,

                                });

                            }

                        }



                        if (candidates.length === 0) return null;



                        // 按分数从高到低排序（最靠下最靠右的在前）

                        candidates.sort((a, b) => b.score - a.score);

                        return candidates[0];

                    }"""

                )



                if btn_info:

                    x, y = btn_info["x"], btn_info["y"]

                    logger.info("找到保存按钮（策略2: JS查找）: text='{}' 位置=({},{})",

                                btn_info["text"], int(x), int(y))

                    await self.page.mouse.click(x, y)

                    saved = True

                    logger.info("✓ 已点击保存按钮（策略2: JS查找）")

            except Exception as e:

                logger.warning("策略2查找保存按钮失败: {}", e)



        # 策略3: 兜底 - 按 Enter 键

        if not saved:

            logger.warning("前两种策略都未找到保存按钮，尝试按 Enter 键兜底...")

            try:

                await self.page.keyboard.press("Enter")

                saved = True

                logger.info("✓ 已按 Enter 键（策略3: 兜底）")

            except Exception as e:

                logger.warning("按 Enter 键失败: {}", e)



        if not saved:

            logger.error("未找到保存按钮！")

            await self._diagnose("保存失败_无保存按钮")

            await self._dump_manage_images_page_info("保存失败")

            return False



        # 等待保存处理（给系统一点时间响应保存操作，触发弹窗）
        wait_after_save = random.uniform(2, 5)
        logger.info(f"点击保存后随机等待 {wait_after_save:.1f}秒...")
        await asyncio.sleep(wait_after_save)

        # 处理确认弹窗（等待弹窗出现并点击确定）

        confirm_result = await self._confirm_popup()



        if not confirm_result:

            logger.warning("确认弹窗处理未完全成功，额外等待确保保存完成")

            # 额外等待一段时间，确保保存操作完成
            wait_extra = random.uniform(3, 5)
            logger.info(f"额外随机等待 {wait_extra:.1f}秒确保保存完成...")
            await asyncio.sleep(wait_extra)



        # 再等待一下，确保保存操作完全完成后再关闭标签页

        wait_final = random.uniform(1, 3)
        logger.info(f"保存完成后随机等待 {wait_final:.1f}秒...")
        await asyncio.sleep(wait_final)



        # 保存完成后关闭管理图片标签页，切回库存页

        await self.close_manage_images_tab()

        return True



    async def close_manage_images_tab(self) -> None:

        """关闭管理图片标签页，切回原库存页标签页。"""

        if self._orig_page is not None:

            try:

                logger.info("关闭管理图片标签页，切回库存页")

                if self._page and not self._page.is_closed():

                    await self._page.close()

                    logger.info("已关闭管理图片标签页")

            except Exception as e:

                logger.warning("关闭管理图片标签页失败: {}", e)

            self._page = self._orig_page

            self._orig_page = None

            logger.info("已切回库存页标签页: {}", self.page.url)

        else:

            logger.debug("无需关闭管理图片标签页（未切换过）")



    async def _confirm_popup(self) -> bool:
        """等待系统弹窗并点击确认/完成按钮。

        改进版：
        1. 改进弹窗容器检测，避免把 overlay 遮罩层当作弹窗
        2. 找到真正的弹窗内容（overlay 内部的对话框）
        3. 增加按文本检测弹窗的方式
        4. 延长等待时间，确保弹窗有足够时间出现
        5. 未检测到弹窗时返回 False，让调用方决定后续处理

        Returns:
            True 表示确认成功，False 表示未检测到弹窗或确认失败
        """
        logger.info("等待保存确认弹窗...")

        # ── 弹窗容器选择器（按精确度排序）──
        popup_container_selectors = [
            # 最精确：Kat 设计系统组件
            "kat-modal",
            "kat-dialog",
            "kat-popover",
            "kat-toast",
            "kat-notification",
            # 标准 ARIA 弹窗
            '[role="dialog"]',
            '[role="alertdialog"]',
            '[aria-modal="true"]',
            # 亚马逊特定组件
            '[data-testid*="modal" i]',
            '[data-testid*="dialog" i]',
            '[data-testid*="popup" i]',
            # 常见的弹窗 class（精确匹配）
            '[class*="modal-content" i]',
            '[class*="dialog-content" i]',
            '[class*="popup-content" i]',
            '[class*="modal-body" i]',
            '[class*="dialog-body" i]',
            # 常见的弹窗 class（较宽泛，放在后面）
            '[class*="modal" i]',
            '[class*="dialog" i]',
            '[class*="popover" i]',
            '[class*="popup" i]',
            '[class*="toast" i]',
            '[class*="notification" i]',
            '[class*="alert" i]',
            '[class*="message" i]',
            # 其他常见弹窗模式
            ".a-modal",
            ".a-dialog",
            '[class*="a-popover" i]',
        ]

        # ── 第一步：轮询等待弹窗出现（最多 60 秒）──
        popup_locator = None
        popup_selector_used = None
        max_wait = 60  # 最多等待 60 秒

        for i in range(max_wait):
            for sel in popup_container_selectors:
                try:
                    loc = self.page.locator(sel).first
                    if await loc.count() > 0 and await loc.is_visible():
                        # 额外验证：确保元素有合理大小，不是整个页面的 overlay
                        try:
                            box = await loc.bounding_box()
                            if box:
                                # 弹窗不应该是整个页面大小
                                # 如果宽度超过页面宽度的 90%，可能是 overlay 而不是弹窗
                                page_width = await self.page.evaluate("() => window.innerWidth")
                                page_height = await self.page.evaluate("() => window.innerHeight")

                                is_too_big = (box["width"] > page_width * 0.9 and
                                              box["height"] > page_height * 0.9)

                                if not is_too_big and box["width"] > 100 and box["height"] > 50:
                                    logger.info("✓ 检测到弹窗容器: {} (第 {} 秒) 大小: {}x{}",
                                                sel, i + 1, int(box["width"]), int(box["height"]))
                                    popup_locator = loc
                                    popup_selector_used = sel
                                    break
                        except Exception:
                            # 如果获取 bounding_box 失败，但元素可见，也认为是弹窗
                            logger.info("✓ 检测到弹窗容器: {} (第 {} 秒)", sel, i + 1)
                            popup_locator = loc
                            popup_selector_used = sel
                            break
                except Exception:
                    continue
            if popup_locator is not None:
                break
            await asyncio.sleep(1)

        # ── 第二步：如果没找到精确弹窗，尝试找 overlay 内部的对话框 ──
        if popup_locator is None:
            logger.info("未找到精确弹窗容器，尝试从 overlay 中查找...")
            try:
                # 找 overlay，然后在里面找对话框
                overlay_selectors = [
                    '[class*="overlay" i]',
                    '[class*="modal-backdrop" i]',
                    '[class*="dialog-backdrop" i]',
                ]
                for overlay_sel in overlay_selectors:
                    try:
                        overlay = self.page.locator(overlay_sel).first
                        if await overlay.count() > 0 and await overlay.is_visible():
                            # 在 overlay 内部找真正的弹窗
                            inner_selectors = [
                                '[role="dialog"]',
                                '[class*="modal" i]',
                                '[class*="dialog" i]',
                                '[class*="popup" i]',
                                "kat-modal",
                                "kat-dialog",
                            ]
                            for inner_sel in inner_selectors:
                                try:
                                    inner = overlay.locator(inner_sel).first
                                    if await inner.count() > 0 and await inner.is_visible():
                                        box = await inner.bounding_box()
                                        if box and box["width"] > 100 and box["height"] > 50:
                                            logger.info("✓ 在 overlay 内找到弹窗: {} > {} (第 {} 秒)",
                                                        overlay_sel, inner_sel, i + 1)
                                            popup_locator = inner
                                            popup_selector_used = f"{overlay_sel} > {inner_sel}"
                                            break
                                except Exception:
                                    continue
                            if popup_locator:
                                break
                    except Exception:
                        continue
            except Exception as e:
                logger.debug("从 overlay 查找弹窗失败: {}", e)

        # ── 第三步：按文本查找弹窗（兜底）──
        if popup_locator is None:
            logger.info("尝试按文本查找弹窗...")
            popup_texts = [
                "已提交更改", "保存成功", "保存完成", "操作成功",
                "Changes submitted", "Save successful", "Success",
                "完成", "Done", "OK",
            ]
            for text in popup_texts:
                try:
                    # 找包含该文本的元素，然后向上找弹窗容器
                    text_el = self.page.locator(f'text={text}').first
                    if await text_el.count() > 0 and await text_el.is_visible():
                        # 向上找弹窗容器
                        try:
                            popup_el = await text_el.evaluate_handle("""el => {
                                let p = el;
                                for (let i = 0; i < 15 && p; i++) {
                                    const cls = (p.className || '').toString();
                                    const role = p.getAttribute && p.getAttribute('role');
                                    if (role === 'dialog' || role === 'alertdialog' ||
                                        cls.includes('modal') || cls.includes('dialog') ||
                                        cls.includes('popup') || cls.includes('popover') ||
                                        cls.includes('toast') || cls.includes('notification')) {
                                        return p;
                                    }
                                    p = p.parentElement;
                                }
                                return null;
                            }""")
                            if popup_el:
                                from playwright.sync_api import Locator
                                # 转换为 locator
                                popup_locator = popup_el.as_locator()
                                logger.info("✓ 按文本找到弹窗: '{}'", text)
                                break
                        except Exception:
                            continue
                except Exception:
                    continue

        if popup_locator is None:
            logger.warning("{} 秒内未检测到确认弹窗容器", max_wait)
            logger.info("可能的原因：1) 保存后无弹窗 2) 弹窗样式特殊 3) 保存处理较慢")
            logger.info("将返回 False，由调用方决定后续处理")
            return False

        # ── 第四步：在弹窗内部查找确认/完成按钮并点击 ──
        logger.info("在弹窗内查找确认按钮...")

        confirm_texts = [
            "完成", "确定", "确认", "好的", "知道了", "我知道了",
            "Done", "OK", "Ok", "okay",
            "Confirm", "Close", "关闭",
            "Yes", "是", "Submit", "提交",
            "保存成功", "成功", "Success",
            "已提交", "已保存",
        ]

        confirmed = False

        # 策略1：在弹窗内用文本匹配点击
        for text in confirm_texts:
            try:
                # 在弹窗容器内查找包含该文本的可点击元素
                btn_selectors = [
                    f'button:has-text("{text}")',
                    f'kat-button:has-text("{text}")',
                    f'[role="button"]:has-text("{text}")',
                    f'a:has-text("{text}")',
                ]
                for btn_sel in btn_selectors:
                    try:
                        btn = popup_locator.locator(btn_sel).first
                        if await btn.count() > 0 and await btn.is_visible():
                            await btn.click(timeout=5000)
                            logger.info("✓ 点击弹窗内确认按钮: {} ({})", text, btn_sel)
                            confirmed = True
                            break
                    except Exception:
                        continue
                if confirmed:
                    break
            except Exception:
                continue

        # 策略2：在弹窗内查找所有按钮，点击最后一个（通常确认按钮在最后）
        if not confirmed:
            try:
                btns = popup_locator.locator('button, kat-button, [role="button"], a')
                cnt = await btns.count()
                if cnt > 0:
                    logger.info("弹窗内找到 {} 个按钮，尝试从后往前点击", cnt)
                    # 从后往前找，找第一个可见且可点击的
                    for j in range(cnt - 1, -1, -1):
                        btn = btns.nth(j)
                        try:
                            if await btn.is_visible() and await btn.is_enabled():
                                # 检查按钮大小，确保是真正的按钮
                                try:
                                    box = await btn.bounding_box()
                                    if box and box["width"] > 30 and box["height"] > 20:
                                        await btn.click(timeout=5000)
                                        logger.info("✓ 点击弹窗内第 {} 个按钮（从后往前）", j + 1)
                                        confirmed = True
                                        break
                                except Exception:
                                    # 大小检查失败，直接点击
                                    await btn.click(timeout=5000)
                                    logger.info("✓ 点击弹窗内第 {} 个按钮（从后往前，无大小检查）", j + 1)
                                    confirmed = True
                                    break
                        except Exception:
                            continue
            except Exception as e:
                logger.debug("策略2失败: {}", e)

        # 策略3：按 Enter 键兜底
        if not confirmed:
            try:
                await self.page.keyboard.press("Enter")
                logger.info("✓ 按 Enter 确认弹窗（兜底）")
                confirmed = True
            except Exception as e:
                logger.warning("按 Enter 失败: {}", e)

        # ── 第五步：等待确认操作完成 ──
        wait_after = int((self.cfg.get("upload", {}) or {}).get("wait_after_save", 3))
        await asyncio.sleep(wait_after)

        if confirmed:
            logger.info("✓ 确认弹窗处理完成")
        else:
            logger.warning("确认弹窗处理失败（找到弹窗但未找到确认按钮）")

        return confirmed


    async def _wait_for_save_button_ready(self) -> None:

        """等待保存按钮从"正在验证"状态变成可点击的"保存并完成"状态。



        上传图片后，右下角按钮会显示"正在验证"，需要等验证完成后

        才会变成"保存并完成"，这时才能点击。

        """

        logger.info("等待保存按钮就绪（验证中 -> 保存并完成）...")



        # 保存按钮的各种文本状态

        validating_texts = [

            "正在验证", "验证中", "处理中", "上传中",

            "Validating", "Processing", "Uploading", "Saving",

        ]



        ready_texts = [

            "保存并完成", "Save and finish", "Save and Finish",

            "Save and complete", "Save & finish", "Save & Finish",

            "保存", "Save", "Submit", "Done", "完成",

        ]



        max_wait = 60  # 最多等 60 秒

        checked = 0



        for i in range(max_wait):

            try:

                # 滚到底部确保能看到按钮

                await self.page.evaluate("() => { window.scrollTo(0, document.body.scrollHeight); }")

                await asyncio.sleep(0.3)



                # 检查页面上是否有"保存并完成"等就绪状态的按钮

                found_ready = False

                for text in ready_texts:

                    try:

                        # 查找包含该文本的按钮

                        btn = self.page.locator(f'button:has-text("{text}")').first

                        if await btn.count() > 0 and await btn.is_visible():

                            # 检查按钮是否可用（不是 disabled 状态）

                            try:

                                is_disabled = await btn.evaluate("el => el.disabled")

                                if not is_disabled:

                                    logger.info("✓ 保存按钮已就绪: {} (第 {} 秒)", text, i + 1)

                                    found_ready = True

                                    break

                            except Exception:

                                # 如果获取 disabled 状态失败，默认认为可用

                                logger.info("✓ 保存按钮已就绪: {} (第 {} 秒)", text, i + 1)

                                found_ready = True

                                break

                    except Exception:

                        continue



                if found_ready:

                    return



                # 检查是否还在验证中

                is_validating = False

                for text in validating_texts:

                    try:

                        btn = self.page.locator(f'text={text}').first

                        if await btn.count() > 0 and await btn.is_visible():

                            is_validating = True

                            break

                    except Exception:

                        continue



                if is_validating and i % 5 == 0:

                    logger.info("  仍在验证中... (第 {} 秒)", i + 1)



            except Exception as e:

                if i % 10 == 0:

                    logger.debug("检查保存按钮状态异常: {}", e)



            checked += 1

            await asyncio.sleep(1)



        logger.warning("{} 秒内保存按钮未就绪，继续执行（可能按钮样式不同）", max_wait)
