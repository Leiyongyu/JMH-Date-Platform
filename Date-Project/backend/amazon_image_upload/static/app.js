// ===== 状态 =====
const state = {
    shops: [],              // 扫描到的店铺列表（包含紫鸟匹配信息）
    shopSkus: {},           // 每个店铺的SKU列表，key是店铺索引
    selectedSkus: {},       // 每个店铺选中的SKU集合，key是店铺索引，value是Set
    shopImages: {},         // 已加载图片缓存：店铺索引 -> SKU -> 图片数组
    selectedImages: {},     // 图片选择：店铺索引 -> SKU -> Set(文件名)
    expandedShops: new Set(), // 展开的店铺索引
    uploadRunning: false,
    ws: null,
    config: null,
    batchShopIndex: null,
    lastTaskAlertId: null,
};

// ===== DOM 元素 =====
const $ = (id) => document.getElementById(id);

function toolUrl(url) {
    if (url.startsWith('/')) return `.${url}`;
    return url;
}

// ===== 工具函数 =====
function toast(msg, type = 'info') {
    const container = $('toastContainer');
    const el = document.createElement('div');
    el.className = `toast ${type}`;
    el.textContent = msg;
    container.appendChild(el);
    setTimeout(() => {
        el.style.opacity = '0';
        el.style.transition = 'opacity 0.3s';
        setTimeout(() => el.remove(), 300);
    }, 3000);
}

function showConfirm(title, message, onOk) {
    $('confirmTitle').textContent = title;
    $('confirmMessage').textContent = message;
    $('confirmModal').style.display = 'flex';
    $('confirmOkBtn').onclick = () => {
        $('confirmModal').style.display = 'none';
        onOk();
    };
    $('confirmCancelBtn').onclick = () => {
        $('confirmModal').style.display = 'none';
    };
}

async function api(url, options = {}) {
    const { quiet = false, ...fetchOptions } = options;
    try {
        const resp = await fetch(toolUrl(url), { credentials: 'same-origin', ...fetchOptions });
        const data = await resp.json();
        if (!resp.ok) {
            const error = new Error(data.error || data.detail || `请求失败 (${resp.status})`);
            error.status = resp.status;
            error.data = data;
            throw error;
        }
        return data;
    } catch (e) {
        if (!quiet) toast(e.message || '请求失败', 'error');
        throw e;
    }
}

// ===== 配置加载 =====
async function loadConfig() {
    try {
        const cfg = await api('/api/config');
        state.config = cfg;

        // 填充设置表单
        $('cfgCompany').value = cfg.ziniao?.company || '';
        $('cfgUsername').value = cfg.ziniao?.username || '';
        $('cfgPassword').value = cfg.ziniao?.configured ? '密码在8小时有效期内' : '未配置或已过期';
        $('cfgClientPath').value = cfg.ziniao?.client_path || '';
        $('cfgSocketPort').value = cfg.ziniao?.socket_port || 16851;
        $('cfgSlowMo').value = cfg.browser?.slow_mo || 300;
        $('cfgTimeout').value = cfg.browser?.timeout || 30000;
        $('cfgRetry').value = cfg.browser?.retry_times || 3;
        const root = cfg.shop_storage?.root || '';
        $('storageRootHint').textContent = root
            ? `固定扫描根目录：${root} · 紫鸟端口 ${cfg.automation?.base_port || 16851}-${(cfg.automation?.base_port || 16851) + (cfg.automation?.max_concurrent || 5) - 1}`
            : '执行主机尚未配置固定扫描根目录 AMAZON_IMAGE_UPLOAD_SHOP_ROOT';
        return cfg;
    } catch (e) {
        console.error('加载配置失败', e);
        return null;
    }
}

// ===== 店铺刷新 =====
async function refreshShops() {
    const btn = $('refreshShopsBtn');
    btn.disabled = true;
    btn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="animation: spin 1s linear infinite"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg> 刷新中...';

    try {
        const result = await api('/api/shops/refresh', { method: 'POST' });
        state.shops = result.shops || [];
        state.shopSkus = {};
        state.selectedSkus = {};
        state.shopImages = {};
        state.selectedImages = {};
        state.expandedShops = new Set();

        $('shopListHint').textContent = `共 ${result.count} 个授权店铺，本次新建 ${result.created_count || 0} 个目录`;
        if (result.root) $('storageRootHint').textContent = `固定扫描根目录：${result.root}`;
        renderShops();
        updateSelectedCounts();
        toast(`已初始化 ${result.count} 个授权店铺，新建 ${result.created_count || 0} 个目录`, 'success');
    } catch (e) {
        // 错误已在 api 函数中 toast
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg> 刷新店铺列表';
    }
}

// ===== 渲染店铺列表 =====
function renderShops() {
    const container = $('shopListContainer');

    if (state.shops.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                    <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>
                    <polyline points="9 22 9 12 15 12 15 22"/>
                </svg>
                <p>尚未加载店铺</p>
                <p class="hint-text">登录后会按紫鸟权限自动初始化固定根目录中的店铺文件夹</p>
            </div>
        `;
        return;
    }

    container.innerHTML = '';

    state.shops.forEach((shop, index) => {
        const card = document.createElement('div');
        card.className = `shop-card ${shop.matched ? 'matched' : 'unmatched'} ${state.expandedShops.has(index) ? 'expanded' : ''}`;
        card.dataset.index = index;

        // 状态标签
        let badges = '';
        badges += '<span class="shop-card-badge matched">目录已初始化</span>';
        if (shop.folder_created) badges += '<span class="shop-card-badge ok">本次新建</span>';
        if (shop.has_excel) {
            badges += '<span class="shop-card-badge ok">有Excel</span>';
        }
        if (shop.has_images) {
            badges += '<span class="shop-card-badge ok">有图片</span>';
        }

        const selectedCount = state.selectedSkus[index]?.size || 0;
        const totalCount = state.shopSkus[index]?.length || 0;
        const canUse = shop.matched && shop.has_excel && shop.has_images;

        card.innerHTML = `
            <div class="shop-card-header">
                <span class="shop-card-title">${shop.ziniao_shop_name || '未命名店铺'}</span>
                <div class="shop-card-badges">${badges}</div>
                ${selectedCount > 0 ? `<span class="shop-card-badge ok">已选 ${selectedCount}</span>` : ''}
                <svg class="shop-card-toggle" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <polyline points="6 9 12 15 18 9"/>
                </svg>
            </div>
            <div class="shop-card-body">
                <div class="shop-card-info">
                    ${shop.shop_name ? `<span>📁 ${shop.shop_name}</span>` : ''}
                    ${shop.path ? `<span>📍 ${shop.path}</span>` : ''}
                </div>
                <div class="shop-folder-actions">
                    <button class="btn btn-secondary btn-sm" data-action="batch-images" data-index="${index}">批量上传图片</button>
                    <button class="btn btn-secondary btn-sm" data-action="browse-images" data-index="${index}">查看/选择图片</button>
                </div>
                ${canUse ? `
                    <div class="shop-sku-header">
                        <span style="font-size:13px;font-weight:600;">SKU 列表 ${totalCount > 0 ? `(${totalCount}个)` : ''}</span>
                        <div class="shop-sku-actions">
                            ${!state.shopSkus[index] ? `
                                <button class="btn btn-secondary btn-sm" data-action="load-skus" data-index="${index}">加载SKU</button>
                            ` : `
                                <button class="btn btn-secondary btn-sm" data-action="select-all" data-index="${index}">选择全部图片</button>
                            `}
                        </div>
                    </div>
                    <div class="shop-sku-list" data-sku-list="${index}">
                        ${!state.shopSkus[index] ? '<p class="hint-text" style="margin:0;">点击「加载SKU」读取该店铺的Excel文件</p>' : ''}
                    </div>
                ` : `
                    <p class="hint-text" style="margin:0;color:var(--warning);">
                        ${!shop.has_excel ? '店铺目录中还没有SKU Excel文件；可先批量上传图片。' :
                          '图片目录中还没有可上传图片；请点击「批量上传图片」。'}
                    </p>
                `}
                <div class="sku-preview" data-sku-preview="${index}" style="display:none;">
                    <div class="sku-preview-title" data-preview-title></div>
                    <div class="sku-preview-images" data-preview-images></div>
                </div>
            </div>
        `;

        container.appendChild(card);
    });

    // 绑定事件
    container.querySelectorAll('.shop-card-header').forEach(header => {
        header.addEventListener('click', (e) => {
            if (e.target.tagName === 'BUTTON') return;
            const index = parseInt(header.closest('.shop-card').dataset.index);
            toggleShopExpand(index);
        });
    });

    container.querySelectorAll('[data-action="load-skus"]').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const index = parseInt(btn.dataset.index);
            loadShopSkus(index);
        });
    });

    container.querySelectorAll('[data-action="select-all"]').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const index = parseInt(btn.dataset.index);
            toggleSelectAllSkus(index);
        });
    });

    container.querySelectorAll('[data-action="batch-images"]').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            openBatchUpload(parseInt(btn.dataset.index));
        });
    });

    container.querySelectorAll('[data-action="browse-images"]').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            showShopImageCatalog(parseInt(btn.dataset.index));
        });
    });

    // 重新填充已加载的SKU列表
    state.shops.forEach((shop, index) => {
        if (state.shopSkus[index]) {
            renderShopSkuList(index);
        }
    });
}

// ===== 展开/收起店铺 =====
function toggleShopExpand(index) {
    if (state.expandedShops.has(index)) {
        state.expandedShops.delete(index);
    } else {
        state.expandedShops.add(index);
    }
    renderShops();
}

// ===== 加载店铺SKU =====
async function loadShopSkus(index) {
    const shop = state.shops[index];
    if (!shop.has_excel) {
        toast('该店铺没有Excel文件', 'warning');
        return;
    }

    // 显示加载状态
    const listEl = document.querySelector(`[data-sku-list="${index}"]`);
    if (listEl) {
        listEl.innerHTML = '<p class="hint-text" style="margin:0;">加载中...</p>';
    }

    try {
        const result = await api(`/api/shop/skus?shop_index=${index}`);
        state.shopSkus[index] = result.skus || [];
        if (!state.selectedSkus[index]) {
            state.selectedSkus[index] = new Set();
        }
        renderShops();
        renderShopSkuList(index);
        toast(`加载到 ${result.count} 个SKU`, 'success');
    } catch (e) {
        if (listEl) {
            listEl.innerHTML = '<p class="hint-text" style="margin:0;color:var(--danger);">加载失败</p>';
        }
    }
}

// ===== 渲染店铺SKU列表 =====
function renderShopSkuList(index) {
    const listEl = document.querySelector(`[data-sku-list="${index}"]`);
    if (!listEl) return;

    const skus = state.shopSkus[index] || [];
    if (skus.length === 0) {
        listEl.innerHTML = '<p class="hint-text" style="margin:0;">Excel中没有SKU</p>';
        return;
    }

    listEl.innerHTML = '';
    const selected = state.selectedSkus[index] || new Set();

    skus.forEach((skuInfo) => {
        const sku = skuInfo.sku;
        const chip = document.createElement('div');
        chip.className = `sku-chip ${selected.has(sku) ? 'selected' : ''} ${!skuInfo.has_images ? 'no-images' : ''}`;
        chip.innerHTML = `
            <input type="checkbox" class="sku-chip-checkbox" ${selected.has(sku) ? 'checked' : ''} ${!skuInfo.has_images ? 'disabled' : ''}>
            <span class="sku-chip-name">${sku}</span>
            ${skuInfo.has_images ? '<span class="sku-chip-img-count">有图</span>' : '<span class="sku-chip-img-count">无图</span>'}
        `;

        chip.addEventListener('click', (e) => {
            if (e.target.type === 'checkbox') {
                toggleSkuSelect(index, sku);
            } else if (skuInfo.has_images) {
                showSkuImages(index, sku);
            }
        });

        listEl.appendChild(chip);
    });
}

function ensureImageSelection(shopIndex, sku) {
    if (!state.shopImages[shopIndex]) state.shopImages[shopIndex] = {};
    if (!state.selectedImages[shopIndex]) state.selectedImages[shopIndex] = {};
    if (!state.selectedImages[shopIndex][sku]) state.selectedImages[shopIndex][sku] = new Set();
    if (!state.selectedSkus[shopIndex]) state.selectedSkus[shopIndex] = new Set();
    return state.selectedImages[shopIndex][sku];
}

async function loadSkuImages(shopIndex, sku) {
    if (state.shopImages[shopIndex]?.[sku]) return state.shopImages[shopIndex][sku];
    const result = await api(`/api/shop/sku/images?shop_index=${shopIndex}&sku=${encodeURIComponent(sku)}`);
    if (!state.shopImages[shopIndex]) state.shopImages[shopIndex] = {};
    state.shopImages[shopIndex][sku] = result.images || [];
    ensureImageSelection(shopIndex, sku);
    return state.shopImages[shopIndex][sku];
}

function syncSkuSelection(shopIndex, sku) {
    const selected = ensureImageSelection(shopIndex, sku);
    if (selected.size > 0) state.selectedSkus[shopIndex].add(sku);
    else state.selectedSkus[shopIndex].delete(sku);
    updateSelectedCounts();
    if (state.shopSkus[shopIndex]) renderShopSkuList(shopIndex);
}

function createImageChoiceCard(shopIndex, sku, imageInfo, allImages) {
    const selected = ensureImageSelection(shopIndex, sku);
    const card = document.createElement('div');
    card.className = `sku-image-choice ${selected.has(imageInfo.name) ? 'selected' : ''}`;

    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.checked = selected.has(imageInfo.name);
    checkbox.className = 'sku-image-checkbox';

    const image = document.createElement('img');
    image.className = 'sku-preview-img';
    const imageUrl = toolUrl(imageInfo.url);
    image.src = imageUrl + (imageUrl.includes('?') ? '&' : '?') + 't=' + Date.now();
    image.alt = imageInfo.name;
    image.title = `点击放大：${imageInfo.name}`;
    image.addEventListener('click', (event) => {
        event.stopPropagation();
        openLightbox(allImages.map(item => toolUrl(item.url)), allImages.indexOf(imageInfo));
    });

    const name = document.createElement('span');
    name.className = 'sku-image-name';
    name.textContent = imageInfo.name;

    const toggle = () => {
        if (selected.has(imageInfo.name)) selected.delete(imageInfo.name);
        else selected.add(imageInfo.name);
        checkbox.checked = selected.has(imageInfo.name);
        card.classList.toggle('selected', checkbox.checked);
        syncSkuSelection(shopIndex, sku);
        const countEl = card.closest('.sku-image-group')?.querySelector('[data-selected-count]');
        if (countEl) countEl.textContent = selected.size;
    };
    checkbox.addEventListener('click', (event) => {
        event.stopPropagation();
        toggle();
    });
    card.addEventListener('click', toggle);
    card.append(checkbox, image, name);
    return card;
}

function appendSkuImageGroup(container, shopIndex, sku, images) {
    const selected = ensureImageSelection(shopIndex, sku);
    const group = document.createElement('div');
    group.className = 'sku-image-group';
    const header = document.createElement('div');
    header.className = 'sku-image-group-header';
    const summary = document.createElement('span');
    const skuName = document.createElement('strong');
    skuName.textContent = sku;
    const selectedCount = document.createElement('span');
    selectedCount.dataset.selectedCount = '';
    selectedCount.textContent = selected.size;
    summary.append(skuName, ` · ${images.length} 张 · 已选 `, selectedCount, ' 张');
    const toggleAll = document.createElement('button');
    toggleAll.type = 'button';
    toggleAll.className = 'btn btn-outline btn-sm';
    toggleAll.textContent = selected.size === images.length && images.length > 0 ? '取消全选' : '全选本SKU';
    toggleAll.addEventListener('click', () => {
        if (selected.size === images.length) selected.clear();
        else images.forEach(image => selected.add(image.name));
        syncSkuSelection(shopIndex, sku);
        renderSkuPreview(shopIndex, [{ sku, images }], `${sku} 图片选择`);
    });
    header.append(summary, toggleAll);
    const grid = document.createElement('div');
    grid.className = 'sku-image-grid';
    images.forEach(image => grid.appendChild(createImageChoiceCard(shopIndex, sku, image, images)));
    group.append(header, grid);
    container.appendChild(group);
}

function renderSkuPreview(shopIndex, groups, title) {
    const previewEl = document.querySelector(`[data-sku-preview="${shopIndex}"]`);
    if (!previewEl) return;
    previewEl.style.display = 'block';
    previewEl.querySelector('[data-preview-title]').textContent = title;
    const imagesEl = previewEl.querySelector('[data-preview-images]');
    imagesEl.innerHTML = '';
    if (!groups.length) {
        imagesEl.innerHTML = '<p class="hint-text" style="margin:0;">没有找到图片</p>';
        return;
    }
    groups.forEach(group => appendSkuImageGroup(imagesEl, shopIndex, group.sku, group.images));
}

// ===== 选中/取消选中SKU的全部图片 =====
async function toggleSkuSelect(shopIndex, sku) {
    const images = await loadSkuImages(shopIndex, sku);
    const selected = ensureImageSelection(shopIndex, sku);
    if (selected.size === images.length && images.length > 0) selected.clear();
    else images.forEach(image => selected.add(image.name));
    syncSkuSelection(shopIndex, sku);
    renderSkuPreview(shopIndex, [{ sku, images }], `${sku} 图片选择`);
}

// ===== 选择/取消选择店铺全部图片 =====
async function toggleSelectAllSkus(shopIndex) {
    const catalog = await api(`/api/shop/images/catalog?shop_index=${shopIndex}`);
    const groups = catalog.items || [];
    if (!state.shopImages[shopIndex]) state.shopImages[shopIndex] = {};
    const allSelected = groups.length > 0 && groups.every(group => {
        state.shopImages[shopIndex][group.sku] = group.images;
        return ensureImageSelection(shopIndex, group.sku).size === group.images.length;
    });
    groups.forEach(group => {
        const selected = ensureImageSelection(shopIndex, group.sku);
        if (allSelected) selected.clear();
        else group.images.forEach(image => selected.add(image.name));
        syncSkuSelection(shopIndex, group.sku);
    });
    renderSkuPreview(shopIndex, groups, `店铺图片库 · ${catalog.image_count || 0} 张`);
}

// ===== 显示SKU图片 =====
async function showSkuImages(shopIndex, sku) {
    const previewEl = document.querySelector(`[data-sku-preview="${shopIndex}"]`);
    if (!previewEl) return;
    previewEl.style.display = 'block';
    previewEl.querySelector('[data-preview-title]').textContent = `${sku} - 加载中...`;
    try {
        const images = await loadSkuImages(shopIndex, sku);
        renderSkuPreview(shopIndex, [{ sku, images }], `${sku} 图片选择`);
    } catch (e) {
        previewEl.querySelector('[data-preview-title]').textContent = `${sku} - 加载失败`;
    }
}

async function showShopImageCatalog(shopIndex) {
    state.expandedShops.add(shopIndex);
    renderShops();
    const previewEl = document.querySelector(`[data-sku-preview="${shopIndex}"]`);
    if (!previewEl) return;
    previewEl.style.display = 'block';
    previewEl.querySelector('[data-preview-title]').textContent = '店铺图片库加载中...';
    try {
        const catalog = await api(`/api/shop/images/catalog?shop_index=${shopIndex}`);
        if (!state.shopImages[shopIndex]) state.shopImages[shopIndex] = {};
        (catalog.items || []).forEach(group => {
            state.shopImages[shopIndex][group.sku] = group.images;
            ensureImageSelection(shopIndex, group.sku);
        });
        renderSkuPreview(shopIndex, catalog.items || [], `店铺图片库 · ${catalog.sku_count || 0} 个SKU / ${catalog.image_count || 0} 张`);
    } catch (e) {
        previewEl.querySelector('[data-preview-title]').textContent = '店铺图片库加载失败';
    }
}

// ===== 图片预览 Lightbox =====
let _modalImages = [];
let _modalIndex = 0;

function openLightbox(images, index) {
    _modalImages = images;
    _modalIndex = index;
    $('imageModal').style.display = 'flex';
    updateModalImage();
}

function updateModalImage() {
    $('imageModalImg').src = _modalImages[_modalIndex];
    $('imageModalInfo').textContent = `${_modalIndex + 1} / ${_modalImages.length}`;
    $('imageModalPrev').disabled = _modalIndex <= 0;
    $('imageModalNext').disabled = _modalIndex >= _modalImages.length - 1;
}

$('imageModalClose').addEventListener('click', () => {
    $('imageModal').style.display = 'none';
});

$('imageModalPrev').addEventListener('click', () => {
    if (_modalIndex > 0) { _modalIndex--; updateModalImage(); }
});

$('imageModalNext').addEventListener('click', () => {
    if (_modalIndex < _modalImages.length - 1) { _modalIndex++; updateModalImage(); }
});

document.addEventListener('keydown', (e) => {
    if ($('imageModal').style.display !== 'flex') return;
    if (e.key === 'Escape') { $('imageModal').style.display = 'none'; }
    if (e.key === 'ArrowLeft' && _modalIndex > 0) { _modalIndex--; updateModalImage(); }
    if (e.key === 'ArrowRight' && _modalIndex < _modalImages.length - 1) { _modalIndex++; updateModalImage(); }
});

// ===== 更新选中数量统计 =====
function updateSelectedCounts() {
    let shopCount = 0;
    let skuCount = 0;
    let imageCount = 0;

    Object.keys(state.selectedSkus).forEach(idx => {
        const count = state.selectedSkus[idx].size;
        if (count > 0) {
            shopCount++;
            skuCount += count;
        }
    });
    Object.values(state.selectedImages).forEach(shopSelection => {
        Object.values(shopSelection || {}).forEach(images => {
            imageCount += images.size;
        });
    });

    $('selectedShopCount').textContent = shopCount;
    $('selectedSkuCount').textContent = skuCount;
    $('selectedImageCount').textContent = imageCount;
    updateStartButton();
}

// ===== 更新开始按钮状态 =====
function updateStartButton() {
    let totalSelected = 0;
    Object.values(state.selectedSkus).forEach(set => {
        totalSelected += set.size;
    });
    $('startUploadBtn').disabled = totalSelected === 0 || state.uploadRunning;
}

// ===== 开始上传 =====
async function startUpload() {
    let totalSelected = 0;
    const shopTasks = [];

    Object.keys(state.selectedSkus).forEach(idx => {
        const index = parseInt(idx);
        const selected = state.selectedSkus[index];
        if (selected && selected.size > 0) {
            const shop = state.shops[index];
            const selectedImages = {};
            Array.from(selected).forEach(sku => {
                selectedImages[sku] = Array.from(state.selectedImages[index]?.[sku] || []);
            });
            shopTasks.push({
                shop_id: shop.ziniao_shop_id,
                shop_name: shop.shop_name,
                excel_path: shop.excel,
                image_root: shop.image_root,
                selected_skus: Array.from(selected),
                selected_images: selectedImages,
            });
            totalSelected += selected.size;
        }
    });

    if (shopTasks.length === 0) {
        toast('请先选择要上传的SKU', 'warning');
        return;
    }

    try {
        const result = await api('/api/upload/start_multi', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ shop_tasks: shopTasks }),
        });
        toast(result.msg || '任务已提交', result.queued ? 'warning' : 'success');
        state.uploadRunning = true;
        updateStartButton();
        // 清空日志
        $('logContainer').innerHTML = '';
        // 重置统计
        $('statTotal').textContent = totalSelected;
        $('statDone').textContent = '0';
        $('statFail').textContent = '0';
        $('statSkip').textContent = '0';
    } catch (e) {
        // 错误已在 api 函数中 toast
    }
}

// ===== 状态更新 =====
function updateStatus(data) {
    state.uploadRunning = Boolean(data.running || data.queued);
    if (data.running || data.queued) {
        $('stopBtn').disabled = false;
        $('connDot').classList.add('connecting');
        $('connText').textContent = data.queued ? `排队第 ${data.queuePosition || 1} 位` : '上传中';
    } else {
        $('stopBtn').disabled = true;
        $('connDot').classList.remove('connecting');
        $('connText').textContent = '未连接';
        $('currentTask').style.display = 'none';
    }
    updateStartButton();
}

// ===== 安全代理轮询 =====
// Java 代理不开放 WebSocket 升级，状态与日志统一通过受保护的 HTTP 接口读取。
async function pollRuntime() {
    try {
        const status = await api('/api/upload/status', { quiet: true });
        updateStatus({
            running: Boolean(status.running),
            queued: Boolean(status.queued),
            queuePosition: Number(status.queue_position || 0),
        });
        $('connDot').classList.add('connected');
        if (!status.running && !status.queued) $('connText').textContent = '服务就绪';

        const task = status.task;
        if (task) {
            if (task.status === 'failed' && task.error_message && state.lastTaskAlertId !== task.task_id) {
                state.lastTaskAlertId = task.task_id;
                toast(task.error_message, 'error');
            }
            const done = Number(task.completed_sku || 0);
            const total = Number(task.total_sku || 0);
            const pct = total > 0 ? Math.min(100, Math.round((done / total) * 100)) : 0;
            $('progressBar').style.width = `${pct}%`;
            $('progressText').textContent = `${done}/${total} (${pct}%)`;
            $('statDone').textContent = done;
            $('statFail').textContent = Number(task.failed_sku || 0);
            $('statSkip').textContent = Number(task.skipped_sku || 0);
            if (status.queued) {
                $('currentTask').style.display = 'block';
                $('currentStep').textContent = `5个端口均忙，当前排队第 ${status.queue_position || 1} 位`;
            } else if (task.current_message && status.running) {
                $('currentTask').style.display = 'block';
                $('currentStep').textContent = task.current_message;
            }
        }

        const logResult = await api('/api/logs?limit=500', { quiet: true });
        const container = $('logContainer');
        container.innerHTML = '';
        (logResult.logs || []).forEach(appendLog);
    } catch (e) {
        $('connDot').classList.remove('connected', 'connecting');
        $('connText').textContent = '连接失败';
    }
}

function connectWS() {
    pollRuntime();
    window.setInterval(pollRuntime, 1500);
}

function appendLog(log) {
    const container = $('logContainer');
    const line = document.createElement('div');
    line.className = `log-line log-${log.level.toLowerCase()}`;
    line.textContent = `[${log.time}] ${log.msg}`;
    container.appendChild(line);
    container.scrollTop = container.scrollHeight;

    // 限制最多500行
    while (container.children.length > 500) {
        container.removeChild(container.firstChild);
    }
}

function updateProgress(data) {
    const { done, total, msg } = data;
    const pct = total > 0 ? Math.round((done / total) * 100) : 0;
    $('progressBar').style.width = `${pct}%`;
    $('progressText').textContent = `${done}/${total} (${pct}%)`;

    if (msg) {
        // 解析消息中的店铺名和SKU
        const match = msg.match(/\[(.+?)\]\s*(.+)/);
        if (match) {
            $('currentSku').textContent = match[1];
            $('currentStep').textContent = match[2];
        } else {
            $('currentSku').textContent = '-';
            $('currentStep').textContent = msg;
        }
        $('currentTask').style.display = 'block';

        // 更新步骤指示器
        const steps = ['打开库存页', '搜索 SKU', '管理图片', '上传图片', '保存完成'];
        document.querySelectorAll('.step').forEach((el, i) => {
            el.classList.remove('active', 'done');
            if (msg.includes(steps[i])) {
                el.classList.add('active');
            }
        });
    }

    // 根据消息更新统计
    if (msg?.includes('完成') || msg?.includes('OK')) {
        const done = parseInt($('statDone').textContent) || 0;
        $('statDone').textContent = done + 1;
    } else if (msg?.includes('失败') || msg?.includes('FAIL')) {
        const fail = parseInt($('statFail').textContent) || 0;
        $('statFail').textContent = fail + 1;
    } else if (msg?.includes('跳过') || msg?.includes('无图片')) {
        const skip = parseInt($('statSkip').textContent) || 0;
        $('statSkip').textContent = skip + 1;
    }
}

// ===== 店铺图片批量上传 =====
function openBatchUpload(index) {
    const shop = state.shops[index];
    if (!shop) return;
    state.batchShopIndex = index;
    $('batchShopName').textContent = shop.ziniao_shop_name || shop.shop_name || '-';
    $('batchShopPath').textContent = shop.image_root || shop.path || '-';
    $('batchImageFiles').value = '';
    $('batchSingleImages').value = '';
    $('batchSku').value = '';
    $('batchOverwrite').checked = false;
    $('batchUploadStatus').textContent = '尚未选择文件';
    $('submitBatchUploadBtn').disabled = false;
    $('batchUploadModal').style.display = 'flex';
}

function closeBatchUpload() {
    if ($('submitBatchUploadBtn').disabled) return;
    $('batchUploadModal').style.display = 'none';
    state.batchShopIndex = null;
}

function makeImageBatches(files) {
    const maxFiles = 50;
    const maxBytes = 45 * 1024 * 1024;
    const maxFileBytes = 30 * 1024 * 1024;
    const allowed = new Set(['jpg', 'jpeg', 'png', 'tif', 'tiff']);
    const batches = [];
    let current = [];
    let currentBytes = 0;
    files.forEach(file => {
        const ext = (file.name.split('.').pop() || '').toLowerCase();
        if (!allowed.has(ext)) throw new Error(`不支持的图片格式：${file.name}`);
        if (file.size > maxFileBytes) throw new Error(`单张图片不能超过30MB：${file.name}`);
        if (current.length > 0 && (current.length >= maxFiles || currentBytes + file.size > maxBytes)) {
            batches.push(current);
            current = [];
            currentBytes = 0;
        }
        current.push(file);
        currentBytes += file.size;
    });
    if (current.length) batches.push(current);
    return batches;
}

async function submitBatchUpload() {
    const shopIndex = state.batchShopIndex;
    const shop = state.shops[shopIndex];
    const folderFiles = Array.from($('batchImageFiles').files || []);
    const singleFiles = Array.from($('batchSingleImages').files || []);
    const files = folderFiles.length > 0 ? folderFiles : singleFiles;
    if (!shop || files.length === 0) {
        toast('请选择图片文件夹，或者选择单张/多张图片', 'warning');
        return;
    }
    if (singleFiles.length > 0 && !$('batchSku').value.trim()) {
        toast('上传单张或多张图片时必须填写固定SKU', 'warning');
        return;
    }

    let batches;
    try {
        batches = makeImageBatches(files);
    } catch (e) {
        toast(e.message, 'error');
        return;
    }
    const submitBtn = $('submitBatchUploadBtn');
    submitBtn.disabled = true;
    $('cancelBatchUploadBtn').disabled = true;
    $('closeBatchUploadBtn').disabled = true;
    let saved = 0;
    let skipped = 0;
    try {
        for (let index = 0; index < batches.length; index++) {
            const form = new FormData();
            form.append('shop_id', shop.ziniao_shop_id);
            form.append('sku', $('batchSku').value.trim());
            form.append('overwrite', $('batchOverwrite').checked ? 'true' : 'false');
            batches[index].forEach(file => {
                form.append('files', file, file.name);
                form.append('relative_paths', file.webkitRelativePath || file.name);
            });
            $('batchUploadStatus').textContent = `正在上传第 ${index + 1}/${batches.length} 批（${batches[index].length} 个文件）...`;
            const result = await api('/api/shop-images/batch-upload', {
                method: 'POST',
                body: form,
            });
            saved += Number(result.saved_count || 0);
            skipped += Number(result.skipped_count || 0);
        }
        $('batchUploadStatus').textContent = `上传完成：保存 ${saved} 个，跳过 ${skipped} 个`;
        const scan = await api('/api/shops/scan', { quiet: true });
        state.shops = scan.shops || state.shops;
        state.shopSkus = {};
        state.selectedSkus = {};
        state.shopImages = {};
        state.selectedImages = {};
        state.expandedShops.add(shopIndex);
        renderShops();
        updateSelectedCounts();
        $('batchUploadModal').style.display = 'none';
        state.batchShopIndex = null;
        if (state.shops[shopIndex]?.has_excel) {
            await loadShopSkus(shopIndex);
        }
        await showShopImageCatalog(shopIndex);
        toast(`图片上传完成：保存 ${saved} 个，跳过 ${skipped} 个`, 'success');
    } catch (e) {
        saved += Number(e.data?.saved_count || 0);
        skipped += Number(e.data?.skipped_count || 0);
        $('batchUploadStatus').textContent = `上传中断：已保存 ${saved} 个、跳过 ${skipped} 个；${e.message}`;
    } finally {
        submitBtn.disabled = false;
        $('cancelBatchUploadBtn').disabled = false;
        $('closeBatchUploadBtn').disabled = false;
    }
}

$('batchImageFiles').addEventListener('change', () => {
    const files = Array.from($('batchImageFiles').files || []);
    if (files.length > 0) $('batchSingleImages').value = '';
    const bytes = files.reduce((sum, file) => sum + file.size, 0);
    $('batchUploadStatus').textContent = `文件夹模式：已选择 ${files.length} 个文件，共 ${(bytes / 1024 / 1024).toFixed(1)}MB；将自动拆批上传`;
});
$('batchSingleImages').addEventListener('change', () => {
    const files = Array.from($('batchSingleImages').files || []);
    if (files.length > 0) $('batchImageFiles').value = '';
    const bytes = files.reduce((sum, file) => sum + file.size, 0);
    $('batchUploadStatus').textContent = `图片模式：已选择 ${files.length} 张，共 ${(bytes / 1024 / 1024).toFixed(1)}MB；请填写固定SKU`;
});
$('closeBatchUploadBtn').addEventListener('click', closeBatchUpload);
$('cancelBatchUploadBtn').addEventListener('click', closeBatchUpload);
$('submitBatchUploadBtn').addEventListener('click', submitBatchUpload);

// ===== 设置弹窗 =====
$('settingsBtn').addEventListener('click', () => {
    $('settingsModal').style.display = 'flex';
});

$('closeSettingsBtn').addEventListener('click', () => {
    $('settingsModal').style.display = 'none';
});

$('resetSettingsBtn').addEventListener('click', () => {
    loadConfig();
});

$('saveSettingsBtn').addEventListener('click', async () => {
    const cfg = {
        browser: {
            slow_mo: parseInt($('cfgSlowMo').value) || 300,
            timeout: parseInt($('cfgTimeout').value) || 30000,
            retry_times: parseInt($('cfgRetry').value) || 3,
        },
    };

    try {
        await api('/api/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(cfg),
        });
        toast('配置已保存', 'success');
        $('settingsModal').style.display = 'none';
        loadConfig();
    } catch (e) {
        // 错误已提示
    }
});

const detectZiniaoBtn = $('detectZiniaoBtn');
detectZiniaoBtn?.addEventListener('click', async () => {
    try {
        const result = await api('/api/ziniao/detect');
        if (result.path) {
            $('cfgClientPath').value = result.path;
            toast(`检测到紫鸟路径: ${result.path}`, 'success');
        } else {
            toast('未检测到紫鸟浏览器，请手动填写路径', 'warning');
        }
    } catch (e) {
        // 错误已提示
    }
});

// ===== 事件绑定 =====
$('refreshShopsBtn').addEventListener('click', refreshShops);
$('startUploadBtn').addEventListener('click', startUpload);

$('stopBtn').addEventListener('click', async () => {
    try {
        await api('/api/upload/stop', { method: 'POST' });
        toast('已发送停止请求', 'warning');
    } catch (e) {
        // 错误已提示
    }
});

$('clearBtn').addEventListener('click', () => {
    showConfirm('清除进度', '确定清除历史上传进度？已上传的任务将重新执行。', async () => {
        try {
            await api('/api/progress/clear', { method: 'POST' });
            toast('已清除历史进度', 'success');
        } catch (e) {}
    });
});

$('clearLogBtn').addEventListener('click', () => {
    $('logContainer').innerHTML = '';
});

// ===== 初始化 =====
window.addEventListener('DOMContentLoaded', async () => {
    if (window.location.search) {
        window.history.replaceState(null, document.title, window.location.pathname);
    }
    const cfg = await loadConfig();
    connectWS();
    if (cfg?.ziniao?.configured && cfg?.shop_storage?.configured) {
        await refreshShops();
    }
});
