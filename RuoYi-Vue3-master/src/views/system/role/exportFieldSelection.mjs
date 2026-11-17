export const EBAY_EXPORT_PERMISSION = 'operations:ebayReplenishmentV2:export'
const FIELD_PREFIX = 'operations:ebayReplenishmentV2:exportColumn:'

/** 局部批量操作，不调用会改变整棵树的 setCheckedKeys/setCheckedNodes。 */
export function setExportBranchChecked(tree, data, checked) {
  if (!tree || data?.perms !== EBAY_EXPORT_PERMISSION) return
  const branch = tree.getNode(data.id)
  if (!branch || branch.disabled) return
  const ancestors = []
  for (let parent = branch.parent; parent && parent.level > 0; parent = parent.parent) {
    ancestors.push({ node: parent, wasGranted: parent.checked || parent.indeterminate })
  }
  function visit(item) {
    for (const child of item.children || []) visit(child)
    if (item.perms !== EBAY_EXPORT_PERMISSION && !item.perms?.startsWith(FIELD_PREFIX)) return
    const node = tree.getNode(item.id)
    if (node && !node.disabled) tree.setChecked(item.id, checked, false)
  }
  visit(data)
  // 非联动模式也补齐必要父级；清空导出时保留原页面访问，不勾选任何兄弟权限。
  for (const { node, wasGranted } of ancestors) {
    if ((checked || wasGranted) && !node.disabled && !node.checked && !node.indeterminate) {
      tree.setChecked(node.key, true, false)
    }
  }
  if (checked) branch.expand()
}
