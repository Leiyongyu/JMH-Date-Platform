"""
报关单生成系统 — 简化版
"""

import datetime, io, re

from flask import Flask, request, jsonify, send_file, render_template

import openpyxl
from backend.customs_declaration import models
from backend.customs_declaration.config import COMPANY_INFO, TEMPLATE_PATH

app = Flask(__name__)

# ==================== 页面 ====================

@app.route('/')
def index():
    return render_template('index.html', company=COMPANY_INFO)


# ==================== 商品查询 ====================

@app.route('/api/search', methods=['GET'])
def api_search():
    """模糊搜索SKU/品名"""
    try:
        q = request.args.get('q', '').strip()
        if not q:
            return jsonify({'success': True, 'data': []})
        results = models.search_products(q, limit=15)
        for item in results:
            for k, v in item.items():
                if hasattr(v, 'isoformat'): item[k] = v.isoformat()
                elif hasattr(v, 'to_eng_string'): item[k] = float(v)
        return jsonify({'success': True, 'data': results})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ==================== 导入历史报关单 ====================

def parse_weight_field(f_val):
    """
    解析「数量及单位」列 (F列)
    格式: "10个/76.8千克" → (数量=10, 单位=个, 总重=76.8, 单重=7.68)
           "7台/10.2千克" → (7, 台, 10.2, 1.457...)
           "8台/17.3千克" → (8, 台, 17.3, 2.1625)
    """
    if not f_val:
        return None, None, None, None
    text = str(f_val).strip()
    # 匹配: 数字+单位/数字+单位
    m = re.match(r'(\d+)\s*([一-龥]+)\s*/\s*([\d.]+)\s*([一-龥]+)', text)
    if m:
        qty = int(m.group(1))
        unit = m.group(2)       # 个/台/只/件
        total_w = float(m.group(3))
        weight_unit = m.group(4)  # 千克/克
        single_w = round(total_w / qty, 4) if qty > 0 else 0
        return qty, unit, total_w, single_w
    return None, None, None, None


def parse_hs_and_desc(b_val):
    """
    解析「商品编号」列 (B列)
    格式: "8414803000 涡轮增压器，单级压缩，..."
    返回: (hs_code, hs_description)
    """
    if not b_val:
        return '', ''
    text = str(b_val).strip()
    # HS编码是前10位数字（有时前4位+后续）
    hs_code = ''
    rest = text
    m = re.match(r'^(\d{4}\s?\d{2,6})', text)
    if m:
        hs_code = m.group(1).replace(' ', '')
        rest = text[m.end():].strip()
    return hs_code, rest


@app.route('/api/import', methods=['POST'])
def api_import():
    """
    上传历史报关单Excel，解析数据行(Row 11+)导入数据库
    表格格式与报关单模版.xlsx 的 Sheet1 相同
    """
    try:
        file = request.files.get('file')
        if not file:
            return jsonify({'success': False, 'error': '请上传文件'}), 400

        wb = openpyxl.load_workbook(io.BytesIO(file.read()), data_only=True)

        # 查找报关单Sheet：优先匹配名称含「报关」的，或第4个sheet，或第一个sheet
        ws = None
        for sn in wb.sheetnames:
            if '报' in sn or '��' in sn:  # 报关/报関
                ws = wb[sn]
                break
        if ws is None and len(wb.sheetnames) >= 4:
            ws = wb.worksheets[3]  # 第4个sheet
        if ws is None:
            ws = wb.worksheets[0]  # 兜底：第一个sheet

        inserted = 0
        updated = 0
        skipped = 0
        errors = []

        # 从第11行开始读取（第10行是表头）
        for row in range(11, ws.max_row + 1):
            sku = str(ws.cell(row=row, column=4).value or '').strip()  # D列=SKU
            if not sku or sku == 'None':
                continue

            # 检查是否已存在
            existing = models.get_product_by_sku(sku)

            # B列: HS编码+申报要素
            b_val = ws.cell(row=row, column=2).value
            hs_code, hs_desc = parse_hs_and_desc(b_val)

            # C列: 商品名称
            desc = str(ws.cell(row=row, column=3).value or '').strip()

            # E列: 规格型号
            model = str(ws.cell(row=row, column=5).value or '').strip()

            # F列: 数量及单位
            f_val = ws.cell(row=row, column=6).value
            qty, unit, total_w, single_w = parse_weight_field(f_val)

            # H列: 原产国
            origin = str(ws.cell(row=row, column=8).value or '').strip()

            # I列: 目的国
            dest = str(ws.cell(row=row, column=9).value or '').strip()

            # K列: 境内货源地
            source = str(ws.cell(row=row, column=11).value or '').strip()

            # M列: 征免
            exemption_val = str(ws.cell(row=row, column=13).value or '').strip()

            # G列: 单价/总价/币制
            g_val = str(ws.cell(row=row, column=7).value or '').strip()
            unit_price_usd, g_currency = 0, 'USD'
            if g_val and '/' in g_val:
                parts = g_val.split('/')
                try: unit_price_usd = float(parts[0])
                except: pass
                if len(parts) >= 3: g_currency = parts[2]

            product = {
                'sku': sku,
                'description_cn': desc,
                'model': model if model else '',
                'unit': unit if unit else '个',
                'unit_price_usd': unit_price_usd,
                'currency': g_currency,
                'single_weight': single_w if single_w else None,
                'hs_code': hs_code,
                'hs_description': hs_desc,
                'origin_country': origin if origin else '',
                'destination_country': dest if dest else '',
                'source_location': source,
                'exemption': exemption_val,
            }

            try:
                models.upsert_product(product)
                if existing:
                    updated += 1
                else:
                    inserted += 1
            except Exception as e:
                errors.append(f'{sku}: {e}')
                skipped += 1

        total = models.get_all_products()
        msg = f'新增 {inserted} 条，更新 {updated} 条'
        if skipped:
            msg += f'，失败 {skipped} 条'
        msg += f'（数据库共 {len(total)} 条）'
        return jsonify({
            'success': True, 'message': msg,
            'inserted': inserted, 'updated': updated,
            'skipped': skipped, 'total': len(total), 'errors': errors
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ==================== 更新单个商品字段 ====================

@app.route('/api/update-product', methods=['POST'])
def api_update_product():
    """保存编辑后的字段到数据库"""
    try:
        data = request.get_json()
        sku = data.get('sku', '').strip()
        field = data.get('field', '').strip()
        value = data.get('value', '')

        if not sku or not field:
            return jsonify({'success': False, 'error': '缺少参数'}), 400

        # 只允许更新指定字段
        allowed_fields = ['hs_code', 'hs_description', 'description_cn', 'model',
                         'unit_price_usd', 'currency', 'origin_country',
                         'destination_country', 'source_location', 'exemption']
        if field not in allowed_fields:
            return jsonify({'success': False, 'error': f'不允许更新字段: {field}'}), 400

        models.update_product_field(sku, field, value)

        return jsonify({'success': True, 'message': f'{field} 已更新'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ==================== 批量查询SKU ====================

@app.route('/api/batch-query', methods=['POST'])
def api_batch_query():
    """上传仅有SKU列的Excel，批量查询返回商品信息"""
    try:
        file = request.files.get('file')
        if not file:
            return jsonify({'success': False, 'error': '请上传文件'}), 400

        wb = openpyxl.load_workbook(io.BytesIO(file.read()), data_only=True)
        ws = wb.worksheets[0]

        items = []
        for row in ws.iter_rows(min_row=1, max_row=ws.max_row, max_col=2):
            sku = str(row[0].value or '').strip() if len(row) > 0 else ''
            if not sku or sku.lower() == 'sku':
                continue
            qty = 1
            if len(row) > 1 and row[1].value is not None:
                try: qty = int(row[1].value)
                except: qty = 1
            items.append({'sku': sku, 'quantity': qty})

        if not items:
            return jsonify({'success': False, 'error': '未读取到SKU'}), 400

        # 查询数据库
        products = []
        errors = []
        for item in items:
            p = models.get_product_by_sku(item['sku'])
            if p:
                entry = dict(p)
                for k, v in entry.items():
                    if hasattr(v, 'isoformat'): entry[k] = v.isoformat()
                    elif hasattr(v, 'to_eng_string'): entry[k] = float(v)
                entry['quantity'] = item['quantity']
                products.append(entry)
            else:
                errors.append(item['sku'])

        return jsonify({
            'success': True,
            'data': products,
            'errors': errors if errors else None
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ==================== 导出报关单 ====================

@app.route('/api/export', methods=['POST'])
def api_export():
    """
    导出报关单Excel（仅第四个Sheet格式）
    """
    try:
        data = request.get_json()
        items = data.get('items', [])
        if not items:
            return jsonify({'success': False, 'error': '请提供商品数据'}), 400

        template_path = TEMPLATE_PATH
        if not template_path.exists():
            return jsonify({'success': False, 'error': '报关单模板未随项目部署'}), 500

        # 加载模板
        wb = openpyxl.load_workbook(template_path)
        ws = wb.worksheets[0]  # Sheet1 就是报关单

        # 第10行是表头，从第11行开始填充数据
        DATA_START = 11

        # --- 设置列宽（修改下面数字即可调整导出Excel各列宽度） ---
        col_widths = {
            'A': 6,   # 项号
            'B': 18,  # 商品编号
            'C': 14,  # 商品名称
            'D': 25,  # SKU/申报要素
            'E': 10,  # 规格型号
            'F': 25,  # 数量及单位
            'G': 16,  # 单价/总价/币制
            'H': 8,   # 原产国
            'I': 10,  # 最终目的国(合并I:J)
            'K': 14,  # 境内货源地(合并K:L)
            'M': 8,   # 征免
        }
        for col_letter, width in col_widths.items():
            ws.column_dimensions[col_letter].width = width
        TEMPLATE_ROWS = 0  # 模板没有预置数据行

        n = len(items)

        # 如果模板有预设空行，先清除
        # 模板只有表头行(1-10)，没有数据行，直接在第11行开始写

        for i, item in enumerate(items):
            row = DATA_START + i
            qty = int(item.get('quantity', 1))
            sku = item.get('sku', '')
            single_w = float(item.get('single_weight', 0) or 0)
            total_w = round(single_w * qty, 4) if single_w else 0
            unit = item.get('unit', '个')

            # A: 序号
            ws.cell(row=row, column=1, value=i + 1)

            # B: HS编码 + 申报要素
            hs_code = item.get('hs_code', '')
            hs_desc = item.get('hs_description', '')
            b_text = f'{hs_code} {hs_desc}'.strip()
            ws.cell(row=row, column=2, value=b_text)

            # C: 商品名称
            ws.cell(row=row, column=3, value=item.get('description_cn', ''))

            # D: SKU
            ws.cell(row=row, column=4, value=sku)

            # E: 规格型号
            ws.cell(row=row, column=5, value=item.get('model', '通用型'))

            # F: 数量及单位 (格式: 10个/76.8千克)
            if total_w > 0:
                ws.cell(row=row, column=6, value=f'{qty}{unit}/{total_w}千克')
            else:
                ws.cell(row=row, column=6, value=f'{qty}{unit}')

            # G: 单价/总价/币制 — 使用DB存储的3个字段值
            usd_price = float(item.get('unit_price_usd', 0) or 0)
            currency = item.get('currency', 'USD') or 'USD'
            if usd_price > 0:
                total_usd = round(usd_price * qty, 2)
                ws.cell(row=row, column=7, value=f'{usd_price}/{total_usd}/{currency}')
            else:
                ws.cell(row=row, column=7, value=f'0/{0}/{currency}')

            # H: 原产国
            ws.cell(row=row, column=8, value=item.get('origin_country', '中国'))

            # I:J 合并 → 最终目的国(地区)
            ws.merge_cells(start_row=row, start_column=9, end_row=row, end_column=10)
            ws.cell(row=row, column=9, value=item.get('destination_country', ''))

            # K:L 合并 → 境内货源地
            ws.merge_cells(start_row=row, start_column=11, end_row=row, end_column=12)
            ws.cell(row=row, column=11, value=item.get('source_location', ''))

            # M: 征免
            ws.cell(row=row, column=13, value=item.get('exemption', ''))

        # --- 清除模板残留的静态数值（毛重813.6、净重772.1、件数68） ---
        try: ws.cell(row=7, column=3).value = ''
        except: pass
        try: ws.cell(row=7, column=4).value = ''
        except: pass
        try: ws.cell(row=7, column=6).value = ''
        except: pass

        # --- 确保模板合并单元格正确 ---
        # 先清除可能被破坏的合并，再重新合并
        existing_merges = {str(r) for r in ws.merged_cells.ranges}
        needed_merges = {
            'B1:L1': (1,2,1,12),     # 标题
            'B8:M8': (8,2,8,13),     # 随附单证
            'B9:M9': (9,2,9,13),     # 标记唛码
            'I10:J10': (10,9,10,10), # 最终目的国
            'K10:L10': (10,11,10,12),# 境内货源地
        }
        for rng_str, (r1,c1,r2,c2) in needed_merges.items():
            if rng_str not in existing_merges:
                try:
                    ws.merge_cells(rng_str)
                except:
                    pass

        # --- 填充表单头部信息（精确匹配模版单元格位置） ---
        header = data.get('header', {})
        if header:
            # Row 2
            if header.get('pre_entry'):        # 预录入编号 → B2
                ws.cell(row=2, column=2, value=header['pre_entry'])
            if header.get('customs_no'):       # 海关编号 → D2(D2:E2合并)
                ws.cell(row=2, column=4, value=header['customs_no'])
            # Row 3
            if header.get('consignor'):        # 发货人 → B3
                ws.cell(row=3, column=2, value=header['consignor'])
            if header.get('customs_area'):     # 海关关区 → D3(D3:E3合并)
                ws.cell(row=3, column=4, value=header['customs_area'])
            if header.get('export_date'):      # 出口日期 → G3(F3是标签)
                ws.cell(row=3, column=7, value=header['export_date'])
            if header.get('declare_date'):     # 申报日期 → I3(I3:J3合并)
                ws.cell(row=3, column=9, value=header['declare_date'])
            if header.get('record_no'):        # 备案号 → L3(L3:M3合并)
                ws.cell(row=3, column=12, value=header['record_no'])
            # Row 4
            if header.get('consignee'):        # 收货人 → B4
                ws.cell(row=4, column=2, value=header['consignee'])
            if header.get('transport_mode'):   # 运输方式 → D4(D4:E4合并)
                ws.cell(row=4, column=4, value=header['transport_mode'])
            if header.get('transport_name'):   # 运输工具名称 → G4(F4是标签)
                ws.cell(row=4, column=7, value=header['transport_name'])
            if header.get('bill_no'):          # 提运单号 → I4(I4:M4合并)
                ws.cell(row=4, column=9, value=header['bill_no'])
            # Row 5
            if header.get('producer'):         # 生产销售单位 → B5
                ws.cell(row=5, column=2, value=header['producer'])
            if header.get('supervision'):      # 监管方式 → D5(D5:E5合并)
                ws.cell(row=5, column=4, value=header['supervision'])
            if header.get('tax_nature'):       # 征免性质 → G5(F5是标签)
                ws.cell(row=5, column=7, value=header['tax_nature'])
            if header.get('license_no'):       # 许可证号 → I5(I5:M5合并)
                ws.cell(row=5, column=9, value=header['license_no'])
            # Row 6
            if header.get('contract_no'):      # 合同协议号 → B6
                ws.cell(row=6, column=2, value=header['contract_no'])
            if header.get('trade_country'):    # 贸易国 → D6(D6:E6合并)
                ws.cell(row=6, column=4, value=header['trade_country'])
            if header.get('dest_country'):     # 运抵国 → G6(F6是标签)
                ws.cell(row=6, column=7, value=header['dest_country'])
            if header.get('dest_port'):        # 指运港 → I6(I6:J6合并)
                ws.cell(row=6, column=9, value=header['dest_port'])
            if header.get('entry_port'):       # 入境口岸 → L6(L6:M6合并)
                ws.cell(row=6, column=12, value=header['entry_port'])
            # Row 7
            if header.get('pack_type'):        # 包装种类 → B7
                ws.cell(row=7, column=2, value=header['pack_type'])
            ws.cell(row=7, column=3, value=f"件数  {header.get('pack_qty', n)}")
            if header.get('gross_wt'):         # 毛重 → D7(D7:E7合并)
                ws.cell(row=7, column=4, value=f"毛重（千克）{header['gross_wt']}")
            if header.get('net_wt'):           # 净重 → F7
                ws.cell(row=7, column=6, value=f"净重（千克）{header['net_wt']}")
            if header.get('trade_term'):       # 成交方式 → G7
                ws.cell(row=7, column=7, value=f"成交方式 {header['trade_term']}")
            if header.get('freight'):          # 运费 → I7(H7是标签)
                ws.cell(row=7, column=9, value=header['freight'])
            if header.get('insurance'):        # 保费 → K7(J7是标签)
                ws.cell(row=7, column=11, value=header['insurance'])
            if header.get('other_fee'):        # 杂费 → M7(L7是标签)
                ws.cell(row=7, column=13, value=header['other_fee'])
            # Row 8: 随附单证 (B8:M8合并)
            if header.get('docs'):
                ws.cell(row=8, column=2, value=header['docs'])
            # Row 9: 标记唛码 (B9:M9合并)
            if header.get('marks'):
                ws.cell(row=9, column=2, value=header['marks'])
        else:
            ws.cell(row=7, column=3, value=f'件数  {n}')

        # --- 给所有单元格加边框 ---
        thin_border = openpyxl.styles.Border(
            left=openpyxl.styles.Side(style='thin'),
            right=openpyxl.styles.Side(style='thin'),
            top=openpyxl.styles.Side(style='thin'),
            bottom=openpyxl.styles.Side(style='thin')
        )
        last_row = DATA_START + n - 1
        for r in range(1, last_row + 1):
            for c in range(1, 14):
                cell = ws.cell(row=r, column=c)
                try:
                    cell.border = thin_border
                except AttributeError:
                    pass

        # 保存
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)

        date_str = datetime.date.today().strftime('%y%m%d')
        filename = f'报关单_{date_str}.xlsx'
        return send_file(output,
                         mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                         as_attachment=True, download_name=filename)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ==================== 数据库管理 ====================

@app.route('/api/init-db', methods=['POST'])
def api_init_db():
    try:
        models.init_database()
        return jsonify({'success': True, 'message': '数据库初始化完成'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


if __name__ == '__main__':
    print('报关单生成系统 v2.0')
    print('http://localhost:5000')
    app.run(debug=False, host='127.0.0.1', port=5000)
