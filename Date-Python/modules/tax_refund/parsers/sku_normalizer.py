"""
SKU 标准化服务
按统一规则对原始 SKU 进行标准化，确保报关单和发票能精确匹配。
"""
import re
import unicodedata


def _trim_trailing_numbers(sku):
    """
    清理 SKU 末尾被 PDF 黏连的价格/重量数字。
    例如: "JMH60028-0286391.80" → "JMH60028-0286"
    策略: 从右往左扫描，删除小数点及之后的数字，然后删除看起来像价格的连续数字。
    """
    if not sku or len(sku) < 4:
        return sku

    # 1. 去掉末尾 .XX 或 .X（小数部分肯定是价格/重量的）
    sku = re.sub(r'\.\d{1,3}$', '', sku)

    # 2. 如果末尾现在全是数字且长度过长（>5位），可能是价格整数部分
    # 找到 SKU 中最后一个字母的位置，之后的数字如果过长则截断
    last_alpha_pos = -1
    for i, ch in enumerate(sku):
        if ch.isalpha():
            last_alpha_pos = i

    if last_alpha_pos >= 0:
        tail = sku[last_alpha_pos + 1:]  # 最后一个字母之后的部分
        # 如果尾部是纯数字或数字+连字符+数字
        # SKU 的产品编号部分通常 3-5 位数字，超过5位的部分可能是价格
        m = re.match(r'^([\d\-]+)', tail)
        if m:
            digits_part = m.group(1)
            # 只保留最后一个连字符后的5位数字，多余的截掉
            parts = digits_part.rsplit('-', 1)
            if len(parts) == 2:
                prefix, suffix = parts
                if len(suffix) > 4:
                    # 后缀过长，截断（SKU产品编号通常3-4位）
                    suffix = suffix[:4]
                sku = sku[:last_alpha_pos + 1] + prefix + '-' + suffix
            else:
                # 没有连字符，直接限制长度
                if len(digits_part) > 5:
                    sku = sku[:last_alpha_pos + 1] + digits_part[:4]

    return sku


def normalize_sku(raw_sku):
    """
    SKU 标准化流程：
    1. 去除首尾空格
    2. 英文字母转大写
    3. 全角字符转半角
    4. 中文横线、长横线统一为英文 "-"
    5. 删除 SKU 内由 PDF 排版产生的空格
    6. 清洗掉混入的中文、价格数字、单位等杂质

    返回: 标准化后的 SKU，如无法识别则返回 None
    """
    if not raw_sku:
        return None

    sku = str(raw_sku).strip()
    if not sku:
        return None

    # 2. 全角字符转半角
    sku = unicodedata.normalize('NFKC', sku)

    # 3. 英文字母转大写
    sku = sku.upper()

    # 4. 各种横线统一为英文 "-"
    sku = re.sub(r'[‐‑‒–—―−－─]', '-', sku)

    # 5. 删除 PDF 排版产生的内部空格（保留字母数字和 - 之间的连续性）
    sku = re.sub(r'(?<=[A-Z0-9])\s+(?=[A-Z0-9])', '', sku)
    sku = re.sub(r'(?<=[A-Z0-9])\s+(?=-)', '', sku)
    sku = re.sub(r'(?<=-)\s+(?=[A-Z0-9])', '', sku)

    # 6. 清洗混入的中文、价格、单位等杂质
    sku = re.sub(r'[一-鿿㐀-䶿]', '', sku)
    sku = re.sub(r'\([^)]*\)', '', sku)
    sku = re.sub(r'\s+\d+\.?\d*\s*(美元|个|台|件|支|套|千克|克|辆)?', '', sku)
    sku = re.sub(r'\s+\d+\.?\d*$', '', sku)

    # 7. 尾部数字清洗：SKU 格式通常是 XXX-XXXX，后面的多余数字是价格/重量残留
    # 例如 "JMH60028-0286391.80" → 去掉 "391.80"，保留 "JMH60028-0286"
    sku = _trim_trailing_numbers(sku)

    # 再次清理
    sku = sku.strip()

    # 7. 验证 SKU 格式：
    #    - 常规 SKU 至少包含一个英文字母；或
    #    - 允许报关资料中使用的分段纯数字 SKU，例如 50113-0112。
    # 普通连续数字、金额和过短的数字分段仍不应被识别为 SKU。
    if not sku or len(sku) < 4:
        return None
    has_letter = bool(re.search(r'[A-Z]', sku))
    is_structured_numeric_sku = bool(re.fullmatch(r'\d{4,}-\d{3,}', sku))
    if not has_letter and not is_structured_numeric_sku:
        return None
    # 不能包含中文字符
    if re.search(r'[一-鿿]', sku):
        return None

    return sku


def extract_sku_from_spec(spec_text):
    """
    从报关单"商品名称及规格型号"或发票"规格型号"中提取完整 SKU。
    支持格式：
    - "0|0|机动车用|不锈钢制|无品牌|JMH60028-0286" → "JMH60028-0286"
    - "JMH10028-0770" → "JMH10028-0770"
    - "||||JMH60130-0777" → "JMH60130-0777"
    """
    if not spec_text:
        return None

    text = str(spec_text).strip()

    # 尝试从管道分隔的字段中提取最后一个非空部分
    if '|' in text:
        parts = [p.strip() for p in text.split('|')]
        # 从后往前找第一个看起来像 SKU 的部分
        for part in reversed(parts):
            if _looks_like_sku(part):
                return part
        # 如果都不像，取最后一个非空部分
        for part in reversed(parts):
            if part:
                return part

    # 没有管道分隔，直接返回整个文本
    return text


def _looks_like_sku(text):
    """判断文本是否像 SKU（包含字母+数字的组合，可能有连字符）"""
    if not text:
        return False
    # SKU 通常包含至少一个字母和一个数字，或特定格式
    has_letter = bool(re.search(r'[A-Za-z]', text))
    has_digit = bool(re.search(r'\d', text))
    has_separator = bool(re.search(r'[-]', text))
    # 至少包含字母+数字，或字母+连字符+数字
    return (has_letter and has_digit) or (has_letter and has_separator)


def extract_product_name(spec_text):
    """
    从报关单"商品名称及规格型号"中提取商品名称（不含 SKU 的描述部分）
    "0|0|机动车用|不锈钢制|无品牌|JMH60028-0286" → "机动车用 不锈钢制 无品牌"
    """
    if not spec_text:
        return ''

    text = str(spec_text).strip()
    if '|' not in text:
        return text

    parts = [p.strip() for p in text.split('|')]

    # 去掉前置的数字分类码（如 0, 1 等）
    meaningful = []
    for part in parts:
        if part and not _looks_like_sku(part) and not part.isdigit():
            meaningful.append(part)

    return ' '.join(meaningful) if meaningful else parts[-1] if parts else ''


def full_normalize(spec_text):
    """
    完整处理：从规格型号文本中提取 SKU 并标准化。
    返回: (sku_original, sku_normalized, product_name)
    """
    sku_original = extract_sku_from_spec(spec_text)
    sku_normalized = normalize_sku(sku_original) if sku_original else None
    product_name = extract_product_name(spec_text)
    return sku_original, sku_normalized, product_name


if __name__ == '__main__':
    # 测试用例
    tests = [
        "0|0|机动车用|不锈钢制|无品牌|JMH60028-0286",
        "0|0|刹车报警线|高端后方车辆内部照明灯光颜色识别|",
        "||||JMH60130-0777",
        "JMH10028-0770",
        "JMH６0028－0286",  # 全角字符
        "JMH30023-0027",
        "",
    ]
    for t in tests:
        orig, norm, name = full_normalize(t)
        print(f"  Input: {t!r}")
        print(f"  → original={orig!r}, normalized={norm!r}, product_name={name!r}")
        print()
