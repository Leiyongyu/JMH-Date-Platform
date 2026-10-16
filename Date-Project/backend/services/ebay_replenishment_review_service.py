from backend.repositories import ebay_replenishment_review_repository as repository
from backend.services.ebay_order_product_key import product_key


def save_review(site, sku, field, expected_version, text='', operator=None, *, confirm=False):
    for label, value, limit in [('站点', site, 100), ('SKU', sku, 255)]:
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
            raise ValueError(f'{label}不能为空且不能超过{limit}个字符')
    key = product_key(site, sku)
    if key is None:
        raise ValueError('不支持的站点或SKU')
    if field not in ('operations', 'development'):
        raise ValueError('无效备注字段')
    if not isinstance(text, str) or len(text) > 2000:
        raise ValueError('备注最多2000个字符')
    if type(expected_version) is not int or expected_version < 0:
        raise ValueError('备注版本无效，请刷新页面')
    if not isinstance(operator, str) or not operator.strip() or len(operator) > 64:
        raise ValueError('操作人无效')
    return repository.save(*key, field, text, expected_version, operator, confirm=confirm)
