import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'

for (const region of ['eu', 'us']) {
  const page = fs.readFileSync(new URL(`../src/views/operations/amz/replenishment/${region}/index.vue`, import.meta.url), 'utf8')

  test(`${region} export waits up to 10 minutes and never saves an error as xlsx`, () => {
    assert.ok(page.includes('const EXPORT_TIMEOUT = 600000'))
    assert.ok(page.includes(`url: '/operations/amz/replenishment/${region}/export'`))
    assert.match(page, /responseType: 'blob', timeout: EXPORT_TIMEOUT/)
    assert.ok(page.includes('if (!blobValidate(res))'))
    assert.ok(page.includes(':loading="exporting"'))
    assert.match(page, /finally \{\s*exporting\.value = false/)
  })
}
