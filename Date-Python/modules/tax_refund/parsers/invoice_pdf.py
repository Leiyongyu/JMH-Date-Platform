"""
发票 PDF 解析模块
==================
解析增值税专用发票 PDF（电子发票），提取发票头和商品行数据。
"""
import re
import os
from datetime import datetime

import pdfplumber

from modules.tax_refund.parsers.sku_normalizer import full_normalize


def parse_invoice_pdf(file_path):
    """
    解析增值税专用发票 PDF。
    返回: (header_dict, items_list, error_msg)
    """
    pdf = pdfplumber.open(file_path)
    full_text = ''
    for page in pdf.pages:
        text = page.extract_text()
        if text:
            full_text += text + '\n'
    pdf.close()

    if not full_text.strip():
        return None, [], 'PDF文本提取失败，可能为扫描件'

    # 清理文本：合并跨行断开的文字
    full_text = _normalize_text(full_text)

    # 解析发票头
    header = _parse_invoice_header(full_text)

    # 解析商品行
    items = _parse_invoice_items(full_text)

    # 校验金额
    if header and items:
        _validate_amounts(header, items)

    return header, items, None


def _normalize_text(text):
    """清理 PDF 提取文本的常见问题"""
    # 合并被换行打断的商品行
    # 发票商品行以 *xxx* 开头，下一行如果是续行（不以*开头），则合并
    lines = text.split('\n')
    merged = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        # 如果当前行看起来像是商品行开始且下一行是续行
        if re.match(r'\*[^*]+\*', line) and i + 1 < len(lines):
            next_line = lines[i + 1].strip()
            # 续行不以 * 开头且不含数字模式
            if next_line and not re.match(r'\*[^*]+\*', next_line) and not re.search(r'\d+%\s*\d', next_line):
                line = line + next_line
                i += 1
        merged.append(line)
        i += 1

    return '\n'.join(merged)


def _parse_invoice_header(text):
    """解析发票头"""
    header = {}

    # 发票号码（优先从标签后提取，失败则全文搜索16-20位数字）
    m = re.search(r'发票号码[：:]\s*(\d{16,20})', text)
    if not m:
        m = re.search(r'(\d{20})', text)  # 20位发票号码
    if not m:
        m = re.search(r'(\d{16,19})', text)  # 16-19位发票号码
    if m:
        header['invoice_no'] = m.group(1)

    # 开票日期（优先从标签后提取，失败则全文搜索）
    m = re.search(r'开票日期[：:]\s*(\d{4})年(\d{1,2})月(\d{1,2})日', text)
    if not m:
        m = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日', text)
    if m:
        try:
            header['invoice_date'] = datetime(
                int(m.group(1)), int(m.group(2)), int(m.group(3))
            ).date()
        except ValueError:
            pass

    # 购买方名称
    m = re.search(r'名称[：:]\s*(.+?有限公司)', text)
    if m:
        header['buyer_name'] = m.group(1).strip()

    # 购买方纳税号
    m = re.search(r'(?:统一社会信用代码/纳税人识别号|纳税人识别号)[：:]\s*(\w{18})', text)
    if m:
        header['buyer_tax_no'] = m.group(1).strip()

    # 销售方名称（第二个"名称"）
    names = re.findall(r'名称[：:]\s*(.+?有限公司)', text)
    if len(names) >= 2:
        header['supplier_name'] = names[1].strip()

    # 销售方纳税号（第二个18位号）
    tax_nos = re.findall(r'(?:统一社会信用代码/纳税人识别号|纳税人识别号)[：:]\s*(\w{18})', text)
    if len(tax_nos) >= 2:
        header['supplier_tax_no'] = tax_nos[1].strip()

    # 合计金额和税额
    m = re.search(r'合\s*计\s*[¥￥]\s*([\d,]+\.?\d*)\s*[¥￥]\s*([\d,]+\.?\d*)', text)
    if m:
        header['total_amount'] = float(m.group(1).replace(',', ''))
        header['total_tax'] = float(m.group(2).replace(',', ''))

    # 价税合计
    m = re.search(r'(?:价税合计|价税合计（大写）).*?\(小写\)\s*[¥￥]\s*([\d,]+\.?\d*)', text)
    if m:
        header['total_with_tax'] = float(m.group(1).replace(',', ''))

    return header


def _parse_invoice_items(text):
    """解析发票商品行 - 逐行解析"""
    items = []

    # 方法1：使用精确正则匹配每个商品行
    # 商品行格式:
    # *税收分类*商品名 规格型号 单位 数量 单价 金额 税率% 税额
    # 注意：数量后面紧跟单价时可能没有空格（如"20"+"111.94"→"20111.94"）
    item_pattern = re.compile(
        r'\*([^*]+)\*(\S+)\s+'        # *税收分类*商品名
        r'(\S+)\s+'                     # 规格型号
        r'(\S+)\s+'                     # 单位
        r'(\d+\.?\d*)\s*'              # 数量（可能紧跟单价无空格）
        r'(\d+\.?\d*)\s+'              # 单价
        r'(\d+\.?\d*)\s+'              # 金额
        r'(\d+\.?\d*)%\s+'             # 税率%
        r'(\d+\.?\d*)'                 # 税额
    )

    matches = item_pattern.findall(text)
    for m in matches:
        product_name = m[1].strip()
        spec = m[2].strip()
        unit = m[3].strip()
        try:
            amount = float(m[6])
        except ValueError:
            continue
        try:
            tax_rate_pct = float(m[7])
        except ValueError:
            tax_rate_pct = 13.0
        try:
            tax_amount = float(m[8])
        except ValueError:
            continue

        # 处理数量+单价粘连的情况
        quantity_raw = m[4]
        unit_price_raw = m[5]
        quantity = float(quantity_raw)
        unit_price = float(unit_price_raw)

        # 校验：如果 数量×单价 与 金额 差异过大，尝试拆分粘连的数字
        if abs(quantity * unit_price - amount) > 0.05:
            qty, uprice = _split_concatenated_qty_price(quantity_raw, amount)
            if qty and uprice:
                quantity = qty
                unit_price = uprice

        sku_original, sku_normalized, _ = full_normalize(spec)

        items.append({
            'invoice_item_no': len(items) + 1,
            'product_name': product_name,
            'product_specification': spec,
            'sku_original': sku_original,
            'sku_normalized': sku_normalized,
            'unit': unit,
            'purchased_quantity': quantity,
            'unit_price': unit_price,
            'taxable_amount': amount,
            'tax_rate': tax_rate_pct / 100.0,
            'tax_amount': tax_amount,
            'refundable_tax_amount': tax_amount,
        })

    # 方法2：如果正则没匹配到，按行扫描
    if not items:
        items = _parse_items_line_by_line(text)

    return items


def _parse_items_line_by_line(text):
    """逐行扫描方式解析商品行"""
    items = []

    # 在"项目名称"和"合计"之间提取
    m = re.search(r'项目名称.*?(?=合\s*计)', text, re.DOTALL)
    if not m:
        return items

    block = m.group(0)

    # 按行处理
    for line in block.split('\n'):
        line = line.strip()
        if not line or '项目名称' in line or '规格型号' in line:
            continue

        # 尝试匹配：末尾必须有 税率% 税额
        m = re.search(
            r'(?:(\d+\.?\d*)%\s*(\d+\.?\d*)\s*)$', line
        )
        if not m:
            continue

        tax_rate_pct = float(m.group(1))
        tax_amount = float(m.group(2))

        # 去掉末尾的税率和税额部分
        prefix = line[:m.start()].strip()

        # 从末尾提取：金额 单价
        # 倒数第二个和第三个数字
        nums = re.findall(r'(\d+\.?\d*)', prefix)
        if len(nums) < 3:
            continue

        # 金额是倒数第一个不含字母的数字
        amount = float(nums[-1])
        unit_price = float(nums[-2])
        quantity = float(nums[-3])

        # 去掉末尾三个数字，得到：描述 单位
        desc_part = prefix
        for n in reversed(nums[-3:]):
            idx = desc_part.rfind(n)
            if idx >= 0:
                desc_part = desc_part[:idx].strip()

        # 最后一部分是单位
        parts = desc_part.rsplit(None, 1)
        if len(parts) == 2:
            name_spec, unit = parts
        else:
            name_spec = desc_part
            unit = ''

        # 从name_spec中提取税收分类、商品名和规格型号
        m2 = re.match(r'\*([^*]+)\*(.+?)\s+(\S+)$', name_spec)
        if m2:
            product_name = m2.group(2).strip()
            spec = m2.group(3).strip()
        else:
            # 最后一段是规格型号
            p = name_spec.rsplit(None, 1)
            if len(p) == 2:
                product_name = p[0]
                spec = p[1]
            else:
                product_name = name_spec
                spec = ''

        sku_original, sku_normalized, _ = full_normalize(spec)

        items.append({
            'invoice_item_no': len(items) + 1,
            'product_name': product_name,
            'product_specification': spec,
            'sku_original': sku_original,
            'sku_normalized': sku_normalized,
            'unit': unit,
            'purchased_quantity': quantity,
            'unit_price': unit_price,
            'taxable_amount': amount,
            'tax_rate': tax_rate_pct / 100.0,
            'tax_amount': tax_amount,
            'refundable_tax_amount': tax_amount,
        })

    return items


def _split_concatenated_qty_price(concat_str, expected_amount):
    """
    处理数量+单价粘连的情况。
    例如 "20111.9469026548673" → 数量=20, 单价=111.9469...
    通过尝试不同分割点，选择 数量×单价≈金额 的分割方式。
    """
    if '.' not in concat_str:
        return None, None

    # 尝试每个可能的分割点
    for split_at in range(1, len(concat_str)):
        left = concat_str[:split_at]
        right = concat_str[split_at:]
        if '.' not in right:
            continue
        try:
            qty = float(left)
            price = float(right)
            if qty > 0 and price > 0 and abs(qty * price - expected_amount) < 0.05:
                return qty, price
        except ValueError:
            continue
    return None, None


def _validate_amounts(header, items):
    """校验发票金额"""
    items_amount = sum(item['taxable_amount'] for item in items)
    items_tax = sum(item['tax_amount'] for item in items)

    header['_amount_diff'] = abs(items_amount - header.get('total_amount', 0))
    header['_tax_diff'] = abs(items_tax - header.get('total_tax', 0))

    tol = 0.03  # 允许3分钱误差

    if header.get('total_amount') and header['_amount_diff'] > tol:
        header['_amount_mismatch'] = True
    if header.get('total_tax') and header['_tax_diff'] > tol:
        header['_tax_mismatch'] = True


def parse_invoice_pdf_full(file_path, file_hash, batch_id, created_by='SYSTEM',
                          declaration_month=None, declaration_batch=None):
    """完整解析，返回记录列表和统计"""
    header, items, error = parse_invoice_pdf(file_path)

    if error:
        return [], {
            'total_count': 0, 'success_count': 0, 'error_count': 0,
            'error_message': error,
        }

    # 按发票号分组计序号
    seq_counter: dict[str, int] = {}
    source_file_name = os.path.basename(file_path)
    records = []
    for i, item in enumerate(items):
        item['invoice_item_no'] = i + 1
        inv_no = header.get('invoice_no', '')
        seq = seq_counter.get(inv_no, 0) + 1
        seq_counter[inv_no] = seq
        record = {
            'invoice_no': header.get('invoice_no', ''),
            'invoice_date': header.get('invoice_date'),
            'invoice_item_no': item['invoice_item_no'],
            'supplier_name': header.get('supplier_name', ''),
            'supplier_tax_no': header.get('supplier_tax_no', ''),
            'buyer_name': header.get('buyer_name', ''),
            'buyer_tax_no': header.get('buyer_tax_no', ''),
            'tax_type': 'V|增值税',
            'product_name': item.get('product_name', ''),
            'product_specification': item.get('product_specification', ''),
            'sku_original': item.get('sku_original'),
            'sku_normalized': item.get('sku_normalized'),
            'unit': item.get('unit', ''),
            'purchased_quantity': item.get('purchased_quantity', 0),
            'unit_price': item.get('unit_price'),
            'taxable_amount': item.get('taxable_amount', 0),
            'tax_rate': item.get('tax_rate', 0.13),
            # 当前原始发票阶段按用户规则先跟随发票税率；后续如有商品退税率表，
            # 应在形成正式申报明细时再覆盖。
            'refund_rate': item.get('tax_rate', 0.13),
            'tax_amount': item.get('tax_amount', 0),
            'refundable_tax_amount': item.get('refundable_tax_amount'),
            'inventory_status': 'AVAILABLE',
            'remark': '',
            'source_file_name': source_file_name,
            'source_file_hash': file_hash,
            'source_page_no': 1,
            'parse_confidence': 0.95,
            'parse_status': 'PENDING',
            'import_batch_id': batch_id,
            'created_by': created_by,
            # 申报信息（可选，从上传表单传入）
            'declaration_month': declaration_month,
            'declaration_batch': declaration_batch,
            'sequence_no': str(seq).zfill(8),
            'relation_no': f'{declaration_month}{declaration_batch}{str(seq).zfill(8)}'
                           if (declaration_month and declaration_batch) else None,
        }
        records.append(record)

    stats = {
        'total_count': len(records),
        'success_count': 0, 'error_count': 0, 'error_message': None,
    }
    return records, stats


if __name__ == '__main__':
    import json
    pdf_path = r'D:\JMH\出口业务收汇情况表\外汇退税\数据源\发票.pdf'
    header, items, error = parse_invoice_pdf(pdf_path)
    print('=== 发票头 ===')
    print(json.dumps(header, ensure_ascii=False, indent=2, default=str))
    print(f'\n=== 商品行 ({len(items)} 条) ===')
    for item in items:
        print(json.dumps(item, ensure_ascii=False, indent=2, default=str))
