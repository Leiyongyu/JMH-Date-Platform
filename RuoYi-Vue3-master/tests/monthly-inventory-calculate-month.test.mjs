import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const view = readFileSync(
  new URL('../src/views/finance/monthlyInventoryReport/index.vue', import.meta.url),
  'utf8'
)

test('calculate rebuilds only the selected report month from its source month', () => {
  const handler = view.split('async function handleCalculate() {', 2)[1]
    ?.split('\nfunction handleUploadCommand(', 1)[0]
  assert.ok(handler)
  assert.match(handler, /const reportMonth = statMonth\.value/)
  assert.match(handler, /const calculationMonth = sourceStatMonth\.value/)
  assert.match(handler, /rebuildMonthlyInventoryReport\(calculationMonth\)/)
  assert.doesNotMatch(handler, /currentNaturalMonth\(\)|previousNaturalMonth\(/)
  assert.match(view, /:disabled="!sourceStatMonth"/)
})
