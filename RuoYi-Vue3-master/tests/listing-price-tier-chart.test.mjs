import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import * as Vue from 'vue'
import { renderToString } from '@vue/server-renderer'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'
import { compile } from '@vue/compiler-dom'
import { pricePresentation } from '../src/components/ListingPriceTierChart/presentation.js'
const file=new URL('../src/components/ListingPriceTierChart/index.vue',import.meta.url)
const source=fs.readFileSync(file,'utf8')
const {descriptor,errors}=parse(source)
const render=new Function('Vue',compile(descriptor.template.content,{mode:'function',prefixIdentifiers:true}).code)(Vue)
const ranges=['< ¥340','¥340–<680','¥680–<1,020','¥1,020–1,690','> ¥1,690']
// 档数随平台变（人民币5档、美元7档），夹具必须跟着 presentation 走，不能写死。
function definitionsOf(platform) {
 const p=pricePresentation(platform)
 return p.names.map((name,i)=>({name,short:p.shorts[i],compact:p.compacts[i],range:p.ranges[i]}))
}
function nodesOf(platform) {
 const tiers=definitionsOf(platform).map((d,i)=>({tier_no:i+1,label:d.name,range:d.range,sku_count:i?0:2,sku_percent:i?'0.00':'100.00'}))
 const child={node_id:'s',scope:'SITE',site:'DE',store_name:'store',currencies:['EUR'],group_sku_count:2,tiers}
 return {child,shop:{...child,node_id:'p',scope:'SHOP',site:'',children:[child]}}
}
function fallbackOf(report) {
 return Object.entries(report?.rate_months || {})
  .filter(([,month])=>month && month!==report?.rate_month).map(([code])=>code).sort()
}
async function html(platform,report,error='') {
 const presentation=pricePresentation(platform)
 report=structuredClone(report)
 for(const parent of report?.items || []) for(const node of [parent,...(parent.children || [])])
  node.tiers.forEach((t,i)=>t.range=presentation.ranges[i])
 const currentDefinitions=definitionsOf(platform)
 const app=Vue.createSSRApp({render,setup:()=>({platform,platformLabel:platform.toUpperCase(),currencyLabel:presentation.label,presentation,report,error,loading:false,load(){},definitions:currentDefinitions,
 colors:currentDefinitions.map((_,i)=>'c'+i),nodeTitle:n=>n.store_name,tierTitle:t=>t.label,anomalyText:()=>'',detailsOpen:false,keyword:'',visibleShops:[],rateDescription:'各币种最新my_rate',ruleDescription:'按人民币分组',
 rateMonths:report?.rate_months || {},fallbackCurrencies:fallbackOf(report),
 refreshTitle:'重新统计',structureOpen:false,
 sourceLabel:presentation.usesFx?`汇率 ${report?.rate_month||'--'} · ${presentation.rateField}`:`单价 ${report?.unit_price_month||'--'} · 批次 ${report?.unit_price_reg_date||'--'}`})})
 for(const name of ['el-button','el-input','el-table','el-table-column','el-dialog']) app.component(name,{setup:(_, {slots})=>()=>name==='el-dialog'?null:Vue.h('span',slots.default?.())})
 // 产品结构弹窗是独立组件，这里只关心它挂没挂上，内容由它自己的用例覆盖。
 app.component('ProductStructure',{setup:()=>()=>Vue.h('div',{class:'product-structure-stub'})})
 app.component('el-alert',{props:['title'],setup:p=>()=>Vue.h('aside',p.title)})
 app.component('el-empty',{props:['description'],setup:p=>()=>Vue.h('aside',p.description)})
 app.directive('loading',{})
 return renderToString(app)
}
test('both platform chart compiles and retains compact layout',()=>{
 assert.deepEqual(errors,[])
 const script=compileScript(descriptor,{id:'price'})
 assert.deepEqual(compileTemplate({source:descriptor.template.content,filename:file.pathname,id:'price',compilerOptions:{bindingMetadata:script.bindings}}).errors,[])
 assert.match(source,/height: 360px/);assert.match(source,/overflow-y: auto/);assert.doesNotMatch(source,/v-html/)
})
test('AMZ CNY五档与eBay USD七档，店铺默认收起、站点可展开',async()=>{
 for(const p of ['amz','ebay']) {
  const out=await html(p,{state:'READY',items:[nodesOf(p).shop],shop_count:1,total_sku_count:2,rate_month:'2026-09',missing_currencies:[]})
  assert.match(out,new RegExp(pricePresentation(p).label+'价格结构'))
  // 人民币仍用业务分层叫法；美元直接显示价格段，不应再出现分层名。
  if(p==='amz'){assert.match(out,/利润核心层/);assert.match(out,/专业\/稀缺层/)}
  else{assert.match(out,/0-5/);assert.match(out,/500\+/);assert.doesNotMatch(out,/利润核心层/)}
  assert.match(out,/<details class="shop-row">/);assert.doesNotMatch(out,/<details[^>]*open/)
  assert.match(out,/DE · EUR/);assert.match(out,/100.00%/);assert.match(out,/展开报表/)
 }
})
test('stale and missing rates have visible warnings',async()=>{
 const out=await html('amz',{state:'READY',items:[],shop_count:0,total_sku_count:0,stale:true,missing_currencies:['GBP']})
 assert.match(out,/月份已更新/);assert.match(out,/GBP 在汇率表中没有任何可用汇率/)
 // 当月没同步时回退到旧月份：不拦报表，但必须显式说明用的不是当月汇率。
 const fell=await html('amz',{state:'READY',items:[],shop_count:0,total_sku_count:0,rate_month:'2026-10',
  missing_currencies:[],rate_months:{EUR:'2026-09',GBP:'2026-09',USD:'2026-10'}})
 assert.match(fell,/EUR、GBP 使用的不是 2026-10 的汇率/)
 // 全部取自当月时不应出现这条提示。
 const current=await html('amz',{state:'READY',items:[],shop_count:0,total_sku_count:0,rate_month:'2026-09',
  missing_currencies:[],rate_months:{EUR:'2026-09',USD:'2026-09'}})
 assert.doesNotMatch(current,/使用的不是/)
 // eBay 不用汇率，汇率相关提示一律不出现。
 const noFx=await html('ebay',{state:'READY',items:[],shop_count:0,total_sku_count:0,rate_month:'2026-10',
  missing_currencies:['GBP'],rate_months:{EUR:'2026-09',USD:'2026-10'}})
 assert.doesNotMatch(noFx,/使用的不是/);assert.doesNotMatch(noFx,/没有任何可用汇率/)
 assert.match(await html('ebay',{state:'EMPTY',items:[]}),/尚未生成美元报表/)
 assert.match(await html('ebay',null,'出错'),/出错/)
})

test('each store and expanded site shows platform currency ranges, counts and percentages without hover',async()=>{
 for(const platform of ['amz','ebay']) {
  const out=await html(platform,{state:'READY',items:[nodesOf(platform).shop],shop_count:1,total_sku_count:2,rate_month:'2026-09',missing_currencies:[]})
  const values=[...out.matchAll(/<div class="tier-values">([\s\S]*?)<\/div>/g)].map(match=>match[1])
  assert.equal(values.length,2,'store summary and site details both have direct labels')
  for(const block of values) {
   const visibleRanges=[...block.matchAll(/<span class="tier-range"><i[^>]*><\/i>([^<]*)<\/span>/g)]
    .map(match=>match[1].replaceAll('&lt;','<').replaceAll('&gt;','>'))
   // 卡片小字放紧凑档名（美元7列时带$的完整区间会折行）；精确区间留在悬浮提示里。
   assert.deepEqual(visibleRanges,pricePresentation(platform).compacts,'platform price bands must be visible text, not just title attributes')
   assert.match(block,/>2 <span class="sku-unit">SKU<\/span>/)
   assert.equal([...block.matchAll(/>0 <span class="sku-unit">SKU<\/span>/g)].length,
    pricePresentation(platform).names.length-1,'zero-count tiers keep their labels')
   assert.match(block,/<small>100.00%<\/small>/)
  }
 }
})
test('homepage gives price charts a separate half-width second row; no platform data swap',()=>{
 const home=fs.readFileSync(new URL('../src/views/index.vue',import.meta.url),'utf8')
 assert.match(home,/AmzOwnerSkuChart v-for/);assert.match(home,/ListingPriceTierChart v-for/)
 assert.match(home,/repeat\(4, minmax/)
 assert.match(home,/<div class="owner-dashboards">\s*<AmzOwnerSkuChart[^>]+\/>\s*<\/div>\s*<div class="price-dashboards">\s*<ListingPriceTierChart/)
 assert.match(home,/\.price-dashboards \{[^}]*grid-template-columns: repeat\(2, minmax\(0, 1fr\)\)/)
 assert.match(home,/@media \(max-width: 639px\) \{ \.owner-dashboards, \.price-dashboards/)
 assert.match(source,/refreshListingPriceTier\(props.platform\)/)
 assert.match(source,/getListingPriceTier\(props.platform, params\)/)
 // eBay 的月份/店铺筛选要真的传给后端，否则选了也只能看当前月。
 assert.match(source,/month: month.value, shop: shop.value/)
 assert.match(source,/row-key="node_id"/)
})

test('eBay 不再用汇率，AMZ 仍用 my_rate；缓存币种不符要拒绝',()=>{
 // eBay 单价来自飞书成交额/成交量，本身就是美元。
 assert.equal(pricePresentation('ebay').usesFx,false)
 assert.equal(pricePresentation('ebay').rateField,'')
 assert.match(pricePresentation('ebay').formula,/总交易额.*总交易量/)
 assert.match(pricePresentation('ebay').formula,/不做任何汇率换算/)
 assert.equal(pricePresentation('amz').usesFx,true)
 assert.deepEqual(pricePresentation('ebay').ranges,['$0–<5','$5–<20','$20–<50','$50–<100','$100–<200','$200–<500','≥ $500'])
 assert.deepEqual(pricePresentation('ebay').names,['0-5','5-20','20-50','50-100','100-200','200-500','500以上'])
 // 美元7档、人民币5档；四个数组长度必须一致，否则前端按下标取名取色会越界。
 for(const platform of ['amz','ebay']) {
  const pres=pricePresentation(platform)
  assert.equal(pres.names.length,platform==='ebay'?7:5)
  assert.equal(pres.shorts.length,pres.names.length)
  assert.equal(pres.compacts.length,pres.names.length)
  assert.equal(pres.ranges.length,pres.names.length)
 }
 assert.equal(pricePresentation('amz').rateField,'my_rate')
 assert.deepEqual(pricePresentation('amz').ranges,ranges)
 assert.match(source,/next.target_currency \|\| 'CNY'/)
 assert.match(source,/报表币种与当前口径不一致/)
})

test('eBay 多一个产品结构按钮并挂载弹窗；AMZ 没有', async () => {
 const report = {state:'READY',items:[],shop_count:0,total_sku_count:0,rate_month:'2026-09',missing_currencies:[]}
 const ebay = await html('ebay', report)
 assert.match(ebay, /产品结构/)
 assert.match(ebay, /product-structure-stub/)
 const amz = await html('amz', report)
 // 数据源是飞书不良交易刊登表，AMZ 没有对应表，不该出现这个入口。
 assert.doesNotMatch(amz, /产品结构/)
 assert.doesNotMatch(amz, /product-structure-stub/)
})

test('eBay 口径说明改成飞书单价来源，不再提汇率换算', () => {
 const source = fs.readFileSync(new URL('../src/components/ListingPriceTierChart/index.vue', import.meta.url), 'utf8')
 assert.match(source, /不良交易刊登/)
 assert.match(source, /总交易额.*总交易量/)
 assert.match(source, /不做任何汇率换算/)
 // 必须写明覆盖面，否则会被当成全部在售商品的价格结构。
 assert.match(source, /只收录有不良交易的刊登/)
})

test('产品结构一页三图、无明细表、保留年份筛选', () => {
 const source = fs.readFileSync(new URL('../src/components/ListingPriceTierChart/ProductStructure.vue', import.meta.url), 'utf8')
 // 三块面板并排；窄屏落一列。
 assert.match(source, /grid-template-columns: repeat\(3, minmax\(0, 1fr\)\)/)
 assert.match(source, /不同价格段销售数量占比/)
 assert.match(source, /不同价格段不良交易率/)
 assert.match(source, /不同价格段转化率/)
 // 只看图，不再渲染明细表。
 assert.doesNotMatch(source, /<el-table/)
 // 年份筛选保留。
 assert.match(source, /v-model="year"/)
})

test('销量图是堆叠百分比柱，不良率图是点到点直线', () => {
 const source = fs.readFileSync(new URL('../src/components/ListingPriceTierChart/ProductStructure.vue', import.meta.url), 'utf8')
 assert.match(source, /type: 'bar', stack: 'total'/)
 // 平滑曲线会在两个月之间插出实际不存在的取值。
 assert.match(source, /smooth: false/)
 assert.doesNotMatch(source, /smooth: true/)
 // 断点不能连起来，否则没有成交的月份会被画成一段假趋势。
 assert.doesNotMatch(source, /connectNulls\s*:/)
})

test('横坐标只显示月份数字，类目值仍保留年月', () => {
 const source = fs.readFileSync(new URL('../src/components/ListingPriceTierChart/ProductStructure.vue', import.meta.url), 'utf8')
 assert.match(source, /formatter: monthLabel/)
 // 年份已经筛过了，不用再在轴上重复；也就不需要旋转标签。
 assert.doesNotMatch(source, /rotate: 45/)
 // 取第6位起的月份并去掉前导零：2026-08 -> 8。
 assert.match(source, /String\(value\)\.slice\(5\)/)
})

test('店铺没有子节点时不渲染展开控件', async () => {
 const { shop } = nodesOf('ebay')
 // eBay 的店铺就是最细粒度，后端不再返回同值的占位子节点。
 const flat = { ...shop, children: [] }
 const out = await html('ebay', {state:'READY',items:[flat],shop_count:1,total_sku_count:2,
                                 rate_month:'',missing_currencies:[]})
 assert.doesNotMatch(out, /<details/)
 assert.doesNotMatch(out, /<summary/)
 assert.doesNotMatch(out, /class="site-row"/)
 // 店铺本身的数字照常显示。
 assert.match(out, /store/)
 assert.match(out, /100.00%/)

 // AMZ 有真实站点，展开控件要保留。
 const tree = nodesOf('amz').shop
 const amz = await html('amz', {state:'READY',items:[tree],shop_count:1,total_sku_count:2,
                                rate_month:'2026-09',missing_currencies:[]})
 assert.match(amz, /<details class="shop-row">/)
 assert.match(amz, /class="site-row"/)
})

test('eBay 卡片同时显示店铺SKU数与去重SKU数；AMZ 保持原样', async () => {
 const { shop } = nodesOf('ebay')
 const ebay = await html('ebay', {state:'READY',items:[{...shop,children:[]}],shop_count:35,
   total_sku_count:435,distinct_sku_count:291,rate_month:'',missing_currencies:[]})
 assert.match(ebay, /435/);assert.match(ebay, /个店铺SKU/)
 // 只写 435 会被读成「有435个商品」，实际只有291个。
 assert.match(ebay, /291/);assert.match(ebay, /个去重SKU/)

 const amz = await html('amz', {state:'READY',items:[nodesOf('amz').shop],shop_count:1,
   total_sku_count:2,rate_month:'2026-09',missing_currencies:[]})
 assert.doesNotMatch(amz, /个去重SKU/);assert.doesNotMatch(amz, /个店铺SKU/)
})
