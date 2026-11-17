const MODULES = ['operations:amzReplenishment', 'operations:ebayReplenishmentV2']

export function isBusinessScopeBranch(data) {
  return MODULES.some(module => data?.perms === `${module}:data`)
}

/** Change only the module's three scope leaves, preserving unrelated permissions. */
export function setBusinessScope(tree, data, scope) {
  if (!tree || !isBusinessScopeBranch(data) || !['self', 'dept', 'all'].includes(scope)) return
  const selected = data.children?.find(child => child.perms === `${data.perms}:${scope}`)
  const branch = tree.getNode(data.id)
  if (!selected || !branch || branch.disabled) return
  for (const child of data.children || []) {
    const node = tree.getNode(child.id)
    if (node && !node.disabled) tree.setChecked(child.id, false, false)
  }
  tree.setChecked(selected.id, true, false)
  // In strict mode explicitly grant the branch and required ancestors, without
  // cascade (otherwise selecting the parent would re-enable "all").
  for (let node = branch; node && node.level > 0; node = node.parent) {
    if (!node.disabled && !node.checked && !node.indeterminate) tree.setChecked(node.key, true, false)
  }
  branch.expand()
}
