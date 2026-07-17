"""
报关单 PDF 解析模块
====================
仅解析标题包含"中华人民共和国海关出口货物报关单"的页面。
使用 pdfplumber 表格提取 + 文本解析双策略。
"""
import re
import os
from datetime import datetime

import fitz
import pdfplumber

from modules.tax_refund.parsers.sku_normalizer import full_normalize


TARGET_TITLE = '中华人民共和国海关出口货物报关单'


def is_target_page(page_text):
    """判断页面是否为海关出口货物报关单页面"""
    return TARGET_TITLE in page_text


def extract_customs_no_from_text(text):
    """从文本中提取18位海关编号"""
    m = re.search(r'\*(\d{18})\*', text)
    if m:
        return m.group(1)
    m = re.search(r'(\d{18})', text)
    return m.group(1) if m else None


def parse_customs_pdf(file_path):
    """
    解析报关单 PDF。
    返回: (header_dict, items_list, target_page_indices, error_msg)
    """
    # 步骤1：用 PyMuPDF 筛选目标页面
    doc = fitz.open(file_path)
    target_pages = []
    all_text = ''
    for i in range(doc.page_count):
        text = doc[i].get_text()
        if is_target_page(text):
            target_pages.append(i)
            all_text += text + '\n'
    doc.close()

    if not target_pages:
        return None, [], [], '未找到报关单目标页面（标题不含"中华人民共和国海关出口货物报关单"）'

    # 步骤2：用 pdfplumber 提取表格数据（包含日期等单据头信息）
    pb = pdfplumber.open(file_path)
    header_table = _extract_header_table(pb, target_pages[0])

    # 步骤3：提取单据头（结合文本和表格）
    header = _parse_header(all_text, header_table)

    # 步骤4：用 pdfplumber 提取商品表格数据
    items = _parse_items_with_pdfplumber_from_pb(pb, target_pages, all_text)
    pb.close()

    # 步骤4：为每个商品补充 SKU
    for item in items:
        spec = item.get('product_specification', '')
        sku_original, sku_normalized, product_name = full_normalize(spec)
        item['sku_original'] = sku_original
        item['sku_normalized'] = sku_normalized
        if not item.get('export_product_name') and product_name:
            item['export_product_name'] = product_name

    return header, items, target_pages, None


def _extract_header_table(pb, page_idx):
    """从 pdfplumber 第1页提取单据头表格，返回 flatten 后的文本列表"""
    page = pb.pages[page_idx]
    tables = page.extract_tables()
    if not tables:
        return []
    # 把所有单元格文本收集起来
    all_cells = []
    for table in tables:
        for row in table:
            for cell in row:
                if cell:
                    all_cells.append(str(cell).strip())
    return all_cells


def _parse_header(text, header_cells=None):
    """从合并文本和pdfplumber表格中提取单据头"""
    header = {}

    # 海关编号
    m = re.search(r'\*(\d{18})\*', text)
    if m:
        header['customs_declaration_no'] = m.group(1)

    # ---- 申报日期：优先从 pdfplumber 表格单元格中提取 ----
    if header_cells:
        for cell in header_cells:
            if '申报日期' in cell:
                m = re.search(r'(\d{8})', cell)
                if m:
                    try:
                        header['declaration_date'] = datetime.strptime(m.group(1), '%Y%m%d').date()
                    except ValueError:
                        pass
                    break

    # 备选：从文本正则提取
    if 'declaration_date' not in header:
        m = re.search(r'申报日期\s*(\d{8})', text)
        if m:
            try:
                header['declaration_date'] = datetime.strptime(m.group(1), '%Y%m%d').date()
            except ValueError:
                pass

    # ---- 出口日期：优先从 pdfplumber 表格单元格中提取 ----
    if header_cells:
        for cell in header_cells:
            if '出口日期' in cell and '申报日期' not in cell:
                m = re.search(r'(\d{8})', cell)
                if m:
                    try:
                        header['export_date'] = datetime.strptime(m.group(1), '%Y%m%d').date()
                    except ValueError:
                        pass
                    break

    if 'export_date' not in header:
        m = re.search(r'出口日期\s*(\d{8})', text)
        if m:
            try:
                header['export_date'] = datetime.strptime(m.group(1), '%Y%m%d').date()
            except ValueError:
                pass

    # 合同协议号
    m = re.search(r'合同协议号\s*\n?\s*(\S+)', text)
    if m:
        contract = m.group(1).strip()
        if contract and contract not in ('杂费', '运费', '保费'):
            header['contract_no'] = contract
    if 'contract_no' not in header:
        # 从表格中找
        for kw in ['FBA', 'JMH', 'PO', 'CI']:
            m = re.search(rf'\b({kw}\w{{5,}})\b', text)
            if m:
                header['contract_no'] = m.group(1)
                break

    # 境外收货人
    m = re.search(r'(Hong Kong[\s\S]{0,80}(?:Limited|Ltd|Co\.?))', text)
    if m:
        header['overseas_consignee'] = m.group(1).strip().replace('\n', ' ')[:255]

    return header


def _parse_items_with_pdfplumber_from_pb(pb, target_pages, full_text):
    """使用 pdfplumber 表格提取商品行（接受已打开的 pdfplumber 对象）"""
    items = []

    # 收集所有目标页面的表格行，并合并多行商品
    raw_rows = []
    for page_idx in target_pages:
        page = pb.pages[page_idx]
        tables = page.extract_tables()
        for table in tables:
            in_items = False
            for row in table:
                if not row or not row[0]:
                    continue
                first = str(row[0] or '').strip()
                # 跳过表头行
                if '项号' in first and '商品编号' in first:
                    in_items = True
                    continue
                if in_items and first:
                    raw_rows.append(row)

    # 处理原始行：合并续行，解析每条商品
    current_parts = []
    for row in raw_rows:
        first_cell = str(row[0] or '').strip()
        # 检查是否新商品行开始（以数字开头，1-999）
        if re.match(r'^\d{1,3}\s+\d{6,13}\s', first_cell):
            # 保存上一个商品
            if current_parts:
                item = _merge_and_parse_item(current_parts)
                if item:
                    items.append(item)
            current_parts = [row]
        else:
            # 续行：追加到当前商品
            current_parts.append(row)

    # 最后一个商品
    if current_parts:
        item = _merge_and_parse_item(current_parts)
        if item:
            items.append(item)

    # 如果表格提取无结果，回退到文本解析
    if not items:
        items = _parse_items_from_text_fallback(full_text)

    return items


def _merge_and_parse_item(rows):
    """合并多行并解析单个商品。
    报关单表格每行格式（以换行分隔）：
      行1: 项号 HS编码 商品名 [重量] [单价] 原产国 目的国 境内货源地 征免
      行2: 0|0|用途|材质|品牌|SKU [总价] (CHN) (DEU) (序号)
      行3: 数量 单位 美元
    """
    if not rows:
        return None

    # 将所有行的所有单元格合并为一个大文本
    all_text_parts = []
    for row in rows:
        for cell in row:
            if cell:
                all_text_parts.append(str(cell).strip())
    full_text = ' '.join(all_text_parts)

    # ---- 按换行拆分 ----
    lines = full_text.split('\n')

    # ---- 1. 解析第一行：项号 HS编码 商品名 ----
    first_line = lines[0].strip() if lines else full_text
    first_parts = first_line.split()
    if len(first_parts) < 3:
        return None

    item_no = first_parts[0]
    hs_code = first_parts[1]

    # 商品名称：找到第一个纯中文词开始，到遇到国家名(中国/德国等)或数字+单位或照章征税为止
    product_name = _extract_product_name_from_first_line(first_parts[2:])
    if not product_name:
        product_name = first_parts[2]

    # ---- 2. 解析规格型号行（含管道符的行） ----
    spec_line = ''
    price_line = ''
    qty_line = ''
    for line in lines[1:]:
        line = line.strip()
        if not line:
            continue
        if '|' in line:
            spec_line = line
        elif re.search(r'\d+\.?\d*\s*(个|台|件|支|套|只|辆|千克)', line) or '美元' in line or 'USD' in line:
            qty_line = line

    # ---- 3. 从完整文本中提取数据 ----
    # SKU 和规格
    sku_original = None
    sku_normalized = None
    spec_text = spec_line if spec_line else ''

    if spec_line:
        # 格式: 0|0|机动车用|不锈钢制|无品牌|JMH60028-0286 [391.80] [(CHN)] ...
        # 先去掉末尾的数字、括号、国家代码
        spec_clean = re.sub(r'\d+\.?\d*\s*(美元|USD)?$', '', spec_line).strip()
        spec_clean = re.sub(r'\(CHN\)|\(DEU\)|\(\d+\)\s*$', '', spec_clean).strip()
        sku_original, sku_normalized, product_desc = full_normalize(spec_clean)
        if product_desc and not spec_text:
            spec_text = product_desc
    else:
        # 没有管道符行，尝试从整个文本提取 SKU
        sku_original, sku_normalized, _ = full_normalize(full_text)

    # 总价（FOB）：在规格行末尾或整个文本中，最后面的那个金额
    total_price = None
    # 先在规格行中找
    if spec_line:
        m = re.search(r'(\d+\.\d{2})\s*\(', spec_line)
        if not m:
            m = re.search(r'(\d+\.\d{2})\s*$', spec_line)
        if m:
            total_price = float(m.group(1))
    # 再在整个文本找美元前面的数字
    if not total_price:
        m = re.search(r'(\d+\.\d{2})\s*美元', full_text)
        if m:
            total_price = float(m.group(1))
    # 回退：取所有带两位小数的数字中最大的
    if not total_price:
        prices = re.findall(r'(\d+\.\d{2})\b', full_text)
        if prices:
            total_price = float(max(prices, key=float))

    # 单价
    unit_price = None
    m = re.search(r'(\d+\.\d{4})', first_line)
    if m:
        unit_price = float(m.group(1))

    # 数量+单位：优先找贸易单位而非重量单位
    quantity, unit = _extract_qty_unit(full_text)

    return {
        'customs_item_no': item_no,
        'export_product_code': hs_code,
        'product_specification': spec_text,
        'export_product_name': product_name,
        'sku_original': sku_original,
        'sku_normalized': sku_normalized,
        'unit': unit,
        'export_quantity': quantity,
        'unit_price': unit_price,
        'fob_amount': total_price,
        'currency_code': 'USD',
    }


def _extract_product_name_from_first_line(parts):
    """从第一行的剩余部分提取商品名称"""
    if not parts:
        return ''
    name_parts = []
    stop_words = {'中国', '德国', '美国', '日本', '韩国', '英国', '法国', '意大利',
                  '照章征税', '美元', 'USD', 'FOB', 'CIF', 'CFR'}
    qty_units = {'千克', '克', '个', '台', '件', '支', '套', '只', '辆'}
    for p in parts:
        if p in stop_words:
            break
        if re.match(r'^\(\d+\)', p):  # (42019) 等地区代码
            break
        if re.match(r'^\d+\.?\d*$', p):  # 纯数字（重量/价格）
            break
        # 数字+单位（如 21千克、10台）
        if re.match(r'^\d+\.?\d*$', p.rstrip(''.join(qty_units))):
            if any(p.endswith(u) for u in qty_units):
                break
        name_parts.append(p)
    return ' '.join(name_parts)


def _extract_qty_unit(text):
    """从文本中提取数量和单位。优先取贸易单位（个/台/件等），千克是重量不是数量。"""
    # 优先匹配贸易单位（非重量单位）
    trade_patterns = [
        (r'(\d+\.?\d*)\s*(个)\b', 2),
        (r'(\d+\.?\d*)\s*(台)\b', 2),
        (r'(\d+\.?\d*)\s*(件)\b', 2),
        (r'(\d+\.?\d*)\s*(支)\b', 2),
        (r'(\d+\.?\d*)\s*(套)\b', 2),
        (r'(\d+\.?\d*)\s*(辆)\b', 2),
        (r'(\d+\.?\d*)\s*(只)\b', 2),
    ]
    for pat, _ in trade_patterns:
        m = re.search(pat, text)
        if m:
            return float(m.group(1)), m.group(2)

    # 没有贸易单位时才用重量单位
    weight_pat = r'(\d+\.?\d*)\s*(千?克)\b'
    m = re.search(weight_pat, text)
    if m:
        return float(m.group(1)), m.group(2)

    return 0, ''


def _extract_total_price(text, merged_cells):
    """提取商品总价（FOB金额）
    报关单格式：数量 单价 总价 美元
    总价 = 数量 × 单价，且总价前面有"美元"标识
    """
    # 策略1：在美元前面的数字中找最大的那个（通常总价 > 单价）
    usd_match = re.search(r'(\d+\.\d{2,4})\s*(?:美元|USD)', text)
    if usd_match:
        return float(usd_match.group(1))

    # 策略2：在全部文本中搜索数字，总价通常约等于 数量×单价
    # 先找所有看起来像金额的数字（含两位小数）
    all_prices = re.findall(r'(\d+\.\d{2})\b', text)
    if all_prices:
        # 取最大的（总价通常大于数量、单价等）
        return float(max(all_prices, key=float))

    # 策略3：回退到列查找
    for col_idx in range(len(merged_cells)):
        cell = str(merged_cells[col_idx]).strip()
        m = re.search(r'(\d+\.\d{2,4})', cell)
        if m:
            val = float(m.group(1))
            if val > 0 and val < 1000000:
                return val

    return None


def _extract_product_name_from_spec(spec_text):
    """从规格型号文本中提取纯商品名称（去除SKU和分类码）"""
    if not spec_text:
        return ''
    text = spec_text.strip()
    if '|' in text:
        parts = [p.strip() for p in text.split('|')]
        meaningful = []
        for p in parts:
            if p and not p.isdigit() and not _is_sku(p):
                meaningful.append(p)
        return ' '.join(meaningful) if meaningful else text
    return text


def _is_sku(text):
    """判断文本是否为 SKU 编码"""
    return bool(re.match(r'^[A-Z0-9][A-Z0-9\-_]{3,}$', text.upper()))


def _parse_items_from_text_fallback(full_text):
    """文本回退解析 - 当表格提取失败时使用"""
    items = []
    # 在"项号"和"海关批注"之间找商品行
    lines = full_text.split('\n')
    in_items = False
    for line in lines:
        line = line.strip()
        if '项号' in line and '商品编号' in line:
            in_items = True
            continue
        if not in_items or not line:
            continue
        if '海关批注' in line or '集装箱号' in line:
            break
        # 尝试匹配项号行
        m = re.match(r'(\d{1,3})\s+(\d{8,13})\s+(.+)', line)
        if m:
            item_no = m.group(1)
            hs_code = m.group(2)
            rest = m.group(3)
            quantity, unit = _extract_qty_unit(rest)
            total_price = _extract_total_price(rest, [rest])
            items.append({
                'customs_item_no': item_no,
                'export_product_code': hs_code,
                'product_specification': rest[:500],
                'export_product_name': '',
                'unit': unit,
                'export_quantity': quantity,
                'unit_price': round(total_price / quantity, 4) if total_price and quantity else None,
                'fob_amount': total_price,
                'currency_code': 'USD',
            })
    return items


def parse_customs_pdf_full(file_path, file_hash, batch_id, created_by='SYSTEM'):
    """完整解析，返回记录列表和统计"""
    header, items, target_pages, error = parse_customs_pdf(file_path)

    if error:
        return [], {
            'total_count': 0, 'success_count': 0, 'error_count': 0,
            'error_message': error,
        }

    source_file_name = os.path.basename(file_path)
    records = []
    for item in items:
        record = {
            'customs_declaration_no': header.get('customs_declaration_no', ''),
            'customs_item_no': item.get('customs_item_no', ''),
            'declaration_date': header.get('declaration_date'),
            'export_date': header.get('export_date'),
            'contract_no': header.get('contract_no'),
            'overseas_consignee': header.get('overseas_consignee'),
            'export_invoice_no': None,
            'agency_certificate_no': None,
            'export_product_code': item.get('export_product_code', ''),
            'export_product_name': item.get('export_product_name', ''),
            'product_specification': item.get('product_specification', ''),
            'sku_original': item.get('sku_original'),
            'sku_normalized': item.get('sku_normalized'),
            'unit': item.get('unit', ''),
            'export_quantity': item.get('export_quantity', 0),
            'unit_price': item.get('unit_price'),
            'fob_amount': item.get('fob_amount'),
            'currency_code': item.get('currency_code', 'USD'),
            'remark': '',
            'source_file_name': source_file_name,
            'source_file_hash': file_hash,
            'source_page_no': target_pages[0] + 1 if target_pages else None,
            'parse_confidence': _estimate_confidence(item),
            'parse_status': 'PENDING',
            'import_batch_id': batch_id,
            'created_by': created_by,
        }
        records.append(record)

    stats = {
        'total_count': len(records),
        'success_count': 0, 'error_count': 0, 'error_message': None,
    }
    return records, stats


def _estimate_confidence(item):
    """估算解析置信度 0~1"""
    checks = ['export_product_code', 'sku_original', 'export_quantity', 'unit', 'fob_amount']
    score = sum(1 for k in checks if item.get(k))
    return round(score / len(checks), 4)


if __name__ == '__main__':
    import json
    pdf_path = r'D:\JMH\出口业务收汇情况表\外汇退税\数据源\报关单.pdf'
    header, items, pages, error = parse_customs_pdf(pdf_path)
    print(f'海关编号: {header.get("customs_declaration_no") if header else "N/A"}')
    print(f'合同号: {header.get("contract_no") if header else "N/A"}')
    print(f'申报日期: {header.get("declaration_date") if header else "N/A"}')
    print(f'出口日期: {header.get("export_date") if header else "N/A"}')
    print(f'目标页码: {[p+1 for p in pages]}')
    print(f'商品条目数: {len(items)}')
    print(f'错误: {error}')
    for item in items[:5]:
        print(json.dumps(item, ensure_ascii=False, indent=2, default=str))
