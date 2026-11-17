import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'

const dir = new URL('../src/assets/icons/svg/jmh/', import.meta.url)
const files = fs.readdirSync(dir).filter(name => name.endsWith('.svg')).sort()
const readme = fs.readFileSync(new URL('README.md', dir), 'utf8')

test('every jmh icon is listed in the README catalog and vice versa', () => {
  const listed = Array.from(readme.matchAll(/^\| `jmh-([a-z0-9-]+)` \| ([a-z0-9-]+\.svg) \|/gm))
  assert.deepEqual(listed.map(match => match[2]).sort(), files)
  for (const [, name, file] of listed) assert.equal(`${name}.svg`, file, 'reference name matches file name')
})

test('icons are recolorable and resizable: no fill, width, height or class', () => {
  for (const file of files) {
    const svg = fs.readFileSync(new URL(file, dir), 'utf8')
    assert.match(svg, /viewBox="/, file)
    assert.doesNotMatch(svg, /\s(fill|width|height|class)=/, file)
    assert.match(file, /^[a-z0-9]+(-[a-z0-9]+)*\.svg$/, `${file} uses kebab-case purpose names`)
  }
})
