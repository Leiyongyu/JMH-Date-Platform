import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import {parse,compileScript,compileTemplate} from '@vue/compiler-sfc'
import {changeText,displayValue} from '../src/components/HomeInventoryDashboard/metric.js'
const source=fs.readFileSync(new URL('../src/components/HomeInventoryDashboard/index.vue',import.meta.url),'utf8')
test('inventory dashboard compiles, four cards and wide age card',()=>{
 const {descriptor,errors}=parse(source);assert.deepEqual(errors,[])
 const script=compileScript(descriptor,{id:'inventory'})
 assert.deepEqual(compileTemplate({source:descriptor.template.content,filename:'index.vue',id:'inventory',compilerOptions:{bindingMetadata:script.bindings}}).errors,[])
 assert.equal((source.match(/<article /g)||[]).length,4)
 assert.match(source,/grid-template-columns: 1fr 1fr 1.65fr 1fr/)
 assert.match(source,/\.change.up \{ color: #d63232/);assert.match(source,/\.change.down \{ color: #168342/)
 assert.match(source,/requestVersion !== version/)
})
test('monthly rates, absolute SKU difference and missing prior data',()=>{
 assert.equal(changeText({delta:3,direction:'up',change_percent:'12.25'}),'较上月 ↑ +12.25%')
 assert.equal(changeText({delta:-3,direction:'down'},true),'较上月 ↓ −3 个')
 assert.match(changeText({delta:null}),/--/)
 assert.match(changeText({delta:3,direction:'up',change_percent:null}),/上月为0/)
 assert.match(changeText({delta:0,direction:'flat'}),/持平/)
 assert.equal(displayValue(null),'--');assert.equal(displayValue(0),'¥ 0.00')
})
test('homepage switch keeps original panels and gates finance permissions',()=>{
 const home=fs.readFileSync(new URL('../src/views/index.vue',import.meta.url),'utf8')
 assert.match(home,/商品分析/);assert.match(home,/库存分析/)
 assert.match(home,/finance:monthlyInventoryReport:list/);assert.match(home,/finance:slowMovingClearance:list/)
 assert.match(home,/AmzOwnerSkuChart v-for/);assert.match(home,/ListingPriceTierChart v-for/)
 assert.match(source,/getHomeInventorySku/);assert.match(source,/保存当月SKU快照/)
})

test('reference styling uses tinted cards without fabricated trends or hidden age values',()=>{
 for(const card of ['total-card','transit-card','age-card','sku-card']) assert.match(source,new RegExp('class="kpi '+card+'"'))
 assert.match(source,/class="board-heading"/)
 assert.match(source,/class="platform-split"/)
 assert.match(source,/<details v-if="report" class="source-note">/)
 assert.match(source,/report.age_buckets\[bucket.key\].value/)
 assert.match(source,/linear-gradient\(155deg, var\(--tint\)/)
 assert.match(source,/@media \(max-width: 1199px\)/)
 assert.match(source,/@media \(max-width: 639px\)/)
 assert.doesNotMatch(source,/sparkline|Math.random|setInterval/)
})
