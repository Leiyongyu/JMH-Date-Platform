/**
 * 报关单生成系统 - 前端
 */

var orderItems = [];      // 已确认的商品列表
var searchTimer = null;
var activeSearchRow = -1; // 当前正在搜索的行索引

function showLoading() { document.getElementById('loadingOverlay').style.display = 'flex'; }
function hideLoading() { document.getElementById('loadingOverlay').style.display = 'none'; }

function showToast(msg, type) {
    type = type || 'success';
    var bg = type === 'error' ? 'bg-danger' : 'bg-success';
    var icon = type === 'error' ? 'bi-exclamation-triangle' : 'bi-check-circle';
    var html = '<div class="toast align-items-center text-white ' + bg + ' border-0"><div class="d-flex"><div class="toast-body"><i class="bi ' + icon + ' me-2"></i>' + msg + '</div><button class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button></div></div>';
    var c = document.getElementById('toastContainer');
    c.insertAdjacentHTML('beforeend', html);
    var t = new bootstrap.Toast(c.lastElementChild, { delay: 3000 }); t.show();
    setTimeout(function() { c.lastElementChild.remove(); }, 3500);
}

function esc(s) { if (!s) return ''; var d = document.createElement('div'); d.textContent = s; return d.innerHTML; }
function fmt(n, d) { d = d || 2; if (n == null || isNaN(n)) return '-'; return Number(n).toFixed(d); }
function el(id) { return document.getElementById(id); }
function val(id) { var e = el(id); return e ? e.value : ''; }

// ==================== 空白行模板 ====================

function createEmptyItem() {
    return {
        sku: '', description_cn: '', model: '', unit: '个',
        unit_price_usd: 0, currency: 'USD',
        single_weight: 0, quantity: 1,
        hs_code: '', hs_description: '',
        origin_country: '', destination_country: '',
        source_location: '', exemption: ''
    };
}

// 初始化：默认一行空白
document.addEventListener('DOMContentLoaded', function() {
    orderItems.push(createEmptyItem());
    renderRows();
    el('defaultQty').addEventListener('change', function() { updateCalcFields(); renderRows(); });
});

// ==================== SKU 行内模糊搜索 ====================

function rowSearch(rowIdx, keyword) {
    clearTimeout(searchTimer);
    activeSearchRow = rowIdx;
    if (!keyword || keyword.trim().length < 1) { closeAllDropdowns(); return; }

    searchTimer = setTimeout(async function() {
        try {
            var res = await fetch('/api/search?q=' + encodeURIComponent(keyword.trim()));
            var data = await res.json();

            // 查找该行的下拉容器
            var dd = document.getElementById('dd_' + rowIdx);
            if (!dd) return;

            if (!data.success || !data.data.length) {
                dd.innerHTML = '<div class="search-item text-muted">未找到</div>';
                dd.style.display = 'block';
                return;
            }

            var html = '';
            data.data.forEach(function(item, i) {
                html += '<div class="search-item" ' +
                    'onmousedown="event.preventDefault();fillRow(' + rowIdx + ',\'' + esc(item.sku) + '\')" ' +
                    'onmouseenter="hoverItem(' + rowIdx + ',' + i + ')">' +
                    '<span class="sku">' + esc(item.sku) + '</span></div>';
            });
            dd.innerHTML = html;
            dd.style.display = 'block';
        } catch (e) { console.error(e); }
    }, 200);
}

function hoverItem(rowIdx, i) {
    var items = document.querySelectorAll('#dd_' + rowIdx + ' .search-item');
    items.forEach(function(el, j) { el.classList.toggle('active', j === i); });
}

async function fillRow(rowIdx, sku) {
    closeAllDropdowns();
    showLoading();
    try {
        var res = await fetch('/api/search?q=' + encodeURIComponent(sku));
        var data = await res.json();
        if (data.success && data.data.length > 0) {
            var p = null;
            for (var j = 0; j < data.data.length; j++) { if (data.data[j].sku === sku) { p = data.data[j]; break; } }
            if (!p) p = data.data[0];

            orderItems[rowIdx] = {
                sku: p.sku,
                description_cn: p.description_cn,
                model: p.model || '',
                unit: p.unit || '个',
                unit_price_usd: parseFloat(p.unit_price_usd || 0),
                currency: p.currency || 'USD',
                single_weight: parseFloat(p.single_weight || 0),
                hs_code: p.hs_code || '',
                hs_description: p.hs_description || '',
                origin_country: p.origin_country || '',
                destination_country: p.destination_country || '',
                source_location: p.source_location || '',
                exemption: p.exemption || '',
                quantity: parseInt(orderItems[rowIdx].quantity || 1)
            };
        }
    } catch (e) { showToast(e.message, 'error'); }
    hideLoading();
    renderRows();
    updateCalcFields();
}

function closeAllDropdowns() {
    document.querySelectorAll('.row-dd').forEach(function(d) { d.style.display = 'none'; });
}

document.addEventListener('click', function(e) {
    if (!e.target.closest('.sku-search-input') && !e.target.closest('.row-dd')) {
        closeAllDropdowns();
    }
});

// ==================== 渲染数据行 ====================

function renderRows() {
    var tbody = el('dataRows');
    var html = '';

    orderItems.forEach(function(item, i) {
        var usd = parseFloat(item.unit_price_usd || 0);
        var total = parseFloat((usd * item.quantity).toFixed(2));
        var currency = item.currency || 'USD';
        var tw = item.single_weight ? item.single_weight * item.quantity : 0;
        var qtyStr = item.quantity + item.unit;
        if (tw > 0) qtyStr += '/' + fmt(tw, 4) + '千克';

        html += '<tr class="data-row">' +
            '<td style="text-align:center">' + (i + 1) + '</td>' +
            // B: 商品编号 — 可编辑
            '<td><input value="' + esc(item.hs_code) + '" onchange="saveField(\'' + esc(item.sku) + '\',' + i + ',\'hs_code\',this.value)" style="font-size:9px;width:100%">' +
            '<input value="' + esc(item.hs_description || '') + '" onchange="saveField(\'' + esc(item.sku) + '\',' + i + ',\'hs_description\',this.value)" style="font-size:9px;width:100%"></td>' +
            // C: 商品名称 — 可编辑
            '<td style="text-align:center"><input value="' + esc(item.description_cn) + '" onchange="saveField(\'' + esc(item.sku) + '\',' + i + ',\'description_cn\',this.value)" style="font-size:10px;width:100%"></td>' +
            // D: SKU — 搜索框（不可编辑）
            '<td><div style="position:relative">' +
            '<input class="sku-search-input" value="' + esc(item.sku) + '" ' +
            'placeholder="输入SKU搜索..." autocomplete="off" ' +
            'oninput="rowSearch(' + i + ',this.value)" onfocus="rowSearch(' + i + ',this.value)" ' +
            'style="font-size:10px;width:100%">' +
            '<div id="dd_' + i + '" class="search-dropdown row-dd" style="display:none;width:100%"></div>' +
            '</div></td>' +
            // E: 规格型号 — 可编辑
            '<td style="text-align:center"><input value="' + esc(item.model) + '" onchange="saveField(\'' + esc(item.sku) + '\',' + i + ',\'model\',this.value)" style="font-size:10px;width:100%"></td>' +
            // F: 数量及单位
            '<td style="text-align:center;white-space:nowrap;font-size:10px">' +
            '<input type="number" value="' + item.quantity + '" min="1" ' +
            'onchange="updateQty(' + i + ',this.value)" ' +
            'style="font-size:9px;width:32px;text-align:center">' +
            '<small>' + esc(item.unit) + '</small>' +
            (tw > 0 ? '<small>/' + fmt(tw, 1) + '千克</small>' : '') + '</td>' +
            // G: 单价/总价/币制
            '<td style="text-align:center;white-space:nowrap;font-size:9px">' +
            '<input type="number" step="0.01" value="' + usd + '" ' +
            'onchange="updatePrice(' + i + ',\'unit_price_usd\',this.value)" ' +
            'style="font-size:9px;width:36px;text-align:center" title="单价">/' +
            '<input type="number" step="0.01" value="' + total + '" readonly ' +
            'style="font-size:9px;width:40px;text-align:center" title="总价">/' +
            '<input value="' + esc(currency) + '" ' +
            'onchange="saveField(\'' + esc(item.sku) + '\',' + i + ',\'currency\',this.value)" ' +
            'style="font-size:9px;width:26px;text-align:center" title="币制">' +
            '</td>' +
            // H: 原产国 — 可编辑
            '<td style="text-align:center"><input value="' + esc(item.origin_country) + '" onchange="saveField(\'' + esc(item.sku) + '\',' + i + ',\'origin_country\',this.value)" style="font-size:10px;width:100%"></td>' +
            // I: 最终目的国 — 可编辑
            '<td style="text-align:center"><input value="' + esc(item.destination_country) + '" onchange="saveField(\'' + esc(item.sku) + '\',' + i + ',\'destination_country\',this.value)" style="font-size:10px;width:100%"></td>' +
            // J: 境内货源地 — 可编辑
            '<td style="text-align:center"><input value="' + esc(item.source_location) + '" onchange="saveField(\'' + esc(item.sku) + '\',' + i + ',\'source_location\',this.value)" style="font-size:10px;width:100%"></td>' +
            // K: 征免 — 可编辑
            '<td style="text-align:center"><input value="' + esc(item.exemption) + '" onchange="saveField(\'' + esc(item.sku) + '\',' + i + ',\'exemption\',this.value)" style="font-size:10px;width:100%"></td>' +
            // L: 操作: + 和 -
            '<td style="text-align:center;white-space:nowrap">' +
            '<img src="/static/icon/jiahao.svg" onclick="addRowAfter(' + i + ')" title="在下方插入一行" ' +
            'style="width:16px;height:16px;cursor:pointer;vertical-align:middle;margin-right:6px">' +
            '<img src="/static/icon/jianhao.svg" onclick="deleteRow(' + i + ')" title="删除此行" ' +
            'style="width:16px;height:16px;cursor:pointer;vertical-align:middle">' +
            '</td></tr>';
    });

    tbody.innerHTML = html;
}

// ==================== 行操作 ====================

async function saveField(sku, i, field, value) {
    // 更新本地状态
    orderItems[i][field] = value;
    // 保存到数据库
    try {
        await fetch('/api/update-product', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ sku: sku, field: field, value: value })
        });
    } catch (e) { console.error('Save error:', e); }
}

function updateQty(i, val) {
    var q = parseInt(val);
    if (isNaN(q) || q < 1) return;
    var item = orderItems[i];
    item.quantity = q;

    // 更新总重显示
    var tw = item.single_weight ? item.single_weight * q : 0;
    var rows = document.querySelectorAll('#dataRows tr');
    if (rows[i]) {
        var cells = rows[i].querySelectorAll('td');
        // F列(index 5): 数量及单位 — 更新重量文字
        var fCell = cells[5];
        if (fCell && tw > 0) {
            var unit = item.unit || '个';
            fCell.innerHTML = '<input type="number" value="' + q + '" min="1" ' +
                'onchange="updateQty(' + i + ',this.value)" ' +
                'style="font-size:9px;width:32px;text-align:center">' +
                '<small>' + esc(unit) + '</small>' +
                '<small>/' + tw.toFixed(1) + '千克</small>';
        }
        // G列(index 6): 单价/总价/币制 — 更新总价
        var gCell = cells[6];
        if (gCell) {
            var usd = parseFloat(item.unit_price_usd || 0);
            var total = parseFloat((usd * q).toFixed(2));
            var currency = item.currency || 'USD';
            gCell.innerHTML = '<input type="number" step="0.01" value="' + usd + '" ' +
                'onchange="updatePrice(' + i + ',\'unit_price_usd\',this.value)" ' +
                'style="font-size:9px;width:36px;text-align:center" title="单价">/' +
                '<input type="number" step="0.01" value="' + total + '" readonly ' +
                'style="font-size:9px;width:40px;text-align:center" title="总价">/' +
                '<input value="' + esc(currency) + '" ' +
                'onchange="saveField(\'' + esc(orderItems[i].sku) + '\',' + i + ',\'currency\',this.value)" ' +
                'style="font-size:9px;width:26px;text-align:center" title="币制">';
        }
    }
    updateCalcFields();
}

async function updatePrice(i, field, val) {
    var v = parseFloat(val);
    if (isNaN(v)) v = 0;
    var item = orderItems[i];
    item[field] = v;
    // 保存单价到数据库
    if (item.sku) {
        try {
            await fetch('/api/update-product', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ sku: item.sku, field: field, value: v })
            });
        } catch (e) { console.error(e); }
    }
    // 更新总价显示
    var q = item.quantity;
    var total = parseFloat((v * q).toFixed(2));
    var rows = document.querySelectorAll('#dataRows tr');
    if (rows[i]) {
        var cells = rows[i].querySelectorAll('td');
        var gCell = cells[6];
        if (gCell) {
            var inputs = gCell.querySelectorAll('input');
            if (inputs.length >= 2) {
                inputs[1].value = total;  // 只更新总价input
            }
        }
    }
    updateCalcFields();
}

function addRowAfter(i) {
    orderItems.splice(i + 1, 0, createEmptyItem());
    renderRows();
    updateCalcFields();
    // 聚焦新行的SKU输入框
    setTimeout(function() {
        var inputs = document.querySelectorAll('.sku-search-input');
        if (inputs[i + 1]) inputs[i + 1].focus();
    }, 100);
}

function deleteRow(i) {
    if (orderItems.length <= 1) { showToast('至少保留一行', 'error'); return; }
    var name = orderItems[i].sku || '空行';
    if (confirm('确定删除第 ' + (i + 1) + ' 行（' + name + '）？')) {
        orderItems.splice(i, 1);
        renderRows();
        updateCalcFields();
        showToast('已删除');
    }
}

function clearAll() {
    if (confirm('清空全部商品行？')) {
        orderItems = [createEmptyItem()];
        renderRows();
        updateCalcFields();
        showToast('已清空');
    }
}

// ==================== 自动计算 ====================

function updateCalcFields() {
    var totalQty = 0;
    orderItems.forEach(function(item) {
        if (!item.sku) return;
        totalQty += parseInt(item.quantity) || 0;
    });
    var count = orderItems.filter(function(x) { return x.sku; }).length;
    el('f_pack_qty').value = count;
    var info = el('infoText');
    if (info) info.textContent = count + '项 ' + totalQty + '件';
}

// ==================== 导入 ====================

async function importExcel(input) {
    var files = input.files;
    if (!files || !files.length) return;
    showLoading();
    var totalIns = 0, totalUpd = 0, totalSkipped = 0, errorFiles = [];
    for (var f = 0; f < files.length; f++) {
        try {
            var fd = new FormData(); fd.append('file', files[f]);
            var res = await fetch('/api/import', { method: 'POST', body: fd });
            var data = await res.json();
            if (data.success) {
                totalIns += (data.inserted || 0);
                totalUpd += (data.updated || 0);
                totalSkipped += (data.skipped || 0);
            } else {
                errorFiles.push(files[f].name);
            }
        } catch (e) { errorFiles.push(files[f].name); }
    }
    var msg = '新增 ' + totalIns + ' 条，更新 ' + totalUpd + ' 条';
    if (totalSkipped) msg += '，失败 ' + totalSkipped + ' 条';
    if (errorFiles.length) msg += '，' + errorFiles.length + ' 个文件出错';
    showToast(msg, (totalSkipped || errorFiles.length) ? 'error' : 'success');
    hideLoading(); input.value = '';
}

// ==================== 批量导入SKU（仅查询填充，不存库） ====================

async function batchImportSkus(input) {
    var file = input.files[0]; if (!file) return;
    showLoading();
    try {
        // 将文件发送到后端解析
        var fd = new FormData(); fd.append('file', file);
        var res = await fetch('/api/batch-query', { method: 'POST', body: fd });
        var resp = await res.json();
        if (resp.success && resp.data.length > 0) {
            orderItems = resp.data.map(function(p) {
                return {
                    sku: p.sku, description_cn: p.description_cn, model: p.model || '',
                    unit: p.unit || '个', unit_price_usd: p.unit_price_usd || 0,
                    currency: p.currency || 'USD', single_weight: p.single_weight || 0,
                    hs_code: p.hs_code || '', hs_description: p.hs_description || '',
                    origin_country: p.origin_country || '', destination_country: p.destination_country || '',
                    source_location: p.source_location || '', exemption: p.exemption || '',
                    quantity: p.quantity || 1
                };
            });
            renderRows();
            updateCalcFields();
            var msg = '已加载 ' + resp.data.length + ' 个商品';
            if (resp.errors) msg += '，' + resp.errors.length + ' 个未找到';
            showToast(msg);
        } else {
            showToast(resp.error || '未找到任何匹配商品', 'error');
        }
    } catch (e) { showToast('导入失败: ' + e.message, 'error'); }
    hideLoading(); input.value = '';
}

// ==================== 导出 ====================

function collectHeaderData() {
    return {
        pre_entry: val('f_pre_entry'), customs_no: val('f_customs_no'),
        consignor: val('f_consignor'), consignee: val('f_consignee'), producer: val('f_producer'),
        contract_no: val('f_contract_no'), customs_area: val('f_customs_area'),
        record_no: val('f_record_no'), entry_port: val('f_entry_port'),
        export_date: val('f_export_date'), declare_date: val('f_declare_date'),
        transport_mode: val('f_transport_mode'), transport_name: val('f_transport_name'),
        bill_no: val('f_bill_no'), supervision: val('f_supervision'), tax_nature: val('f_tax_nature'),
        license_no: val('f_license_no'), trade_country: val('f_trade_country'),
        dest_country: val('f_dest_country'), dest_port: val('f_dest_port'),
        pack_type: val('f_pack_type'), pack_qty: val('f_pack_qty'),
        gross_wt: val('f_gross_wt'), net_wt: val('f_net_wt'),
        trade_term: val('f_trade_term'),
        freight: val('f_freight'), insurance: val('f_insurance'), other_fee: val('f_other_fee'),
        docs: val('f_docs'), marks: val('f_marks'),
    };
}

async function exportExcel() {
    // 只导出有SKU的行
    var items = orderItems.filter(function(x) { return x.sku; });
    if (!items.length) { showToast('请先添加商品', 'error'); return; }

    // 直接使用 orderItems（已通过 saveField/updateQty/updatePrice 实时更新）
    var exportItems = items.map(function(item) {
        return JSON.parse(JSON.stringify(item));
    });

    showLoading();
    try {
        var res = await fetch('/api/export', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ items: exportItems, header: collectHeaderData() })
        });
        if (!res.ok) { var e = await res.json(); throw new Error(e.error); }
        var blob = await res.blob();
        var url = window.URL.createObjectURL(blob);
        var a = document.createElement('a'); a.href = url; a.download = '报关单.xlsx';
        document.body.appendChild(a); a.click();
        window.URL.revokeObjectURL(url); a.remove();
        showToast('导出成功！');
    } catch (e) { showToast('导出失败: ' + e.message, 'error'); }
    hideLoading();
}
