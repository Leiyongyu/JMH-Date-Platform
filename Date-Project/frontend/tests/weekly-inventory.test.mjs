import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import vm from 'node:vm'
import scripts from '../src/scripts.js'
import { resolveScriptUrl } from '../src/scriptUrl.js'

const html=fs.readFileSync(new URL('../public/weekly-inventory/index.html',import.meta.url),'utf8')
const source=html.match(/<script>([\s\S]*?)<\/script>/)[1]
const flush=()=>new Promise(resolve=>setImmediate(resolve))

function environment(session='token', snapshot={snapshot_date:'2026-09-10',pulled_at:'2026-09-10T10:00:00'}) {
 const elements=new Map(),calls=[]
 function element(){return {children:[],textContent:'',className:'',disabled:false,append(...values){this.children.push(...values)},replaceChildren(){this.children=[]}}}
 const document={getElementById(id){if(!elements.has(id))elements.set(id,element());return elements.get(id)},createElement:element}
 const sandbox={document,URL,URLSearchParams,console,location:{href:`https://erp.example/prod-api/sop/weekly-inventory/proxy/index.html?erp_session=${session}&api_base=https://evil.example/`,pathname:'/prod-api/sop/weekly-inventory/proxy/index.html',search:`?erp_session=${session}&api_base=https://evil.example/`},
 history:{replaceState(){}},window:{addEventListener(){}},confirm:()=>true,setInterval:()=>1,clearInterval(){},setTimeout,
 fetch:async(url,options)=>{calls.push({url:String(url),options});return {ok:true,json:async()=>options.method==='POST'?{request_id:'test',message:'accepted'}:{items:[],total:0,latest_snapshot:snapshot}}}}
 vm.runInNewContext(source,sandbox)
 return {elements,calls,sandbox}
}

test('registered component uses independent authenticated Java proxy',()=>{
 const weekly=scripts.find(s=>s.code==='weekly-inventory-export')
 assert.equal(weekly.permission,'sop:weeklyInventory:use')
 assert.equal(weekly.needSession,true)
 globalThis.window={location:{href:'https://python.example/script-tools/',origin:'https://python.example'}}
 try {
  const url=new URL(resolveScriptUrl(weekly,{imageProxyBase:'https://erp.example/prod-api/sop/image-sop/proxy',erpSession:'session'}))
  assert.equal(url.pathname,'/prod-api/sop/weekly-inventory/proxy/index.html')
  assert.equal(url.origin,'https://erp.example')
  assert.equal(url.searchParams.get('erp_session'),'session')
 }finally{delete globalThis.window}
})

test('page requests stay on same origin and preserve list pagination',async()=>{
 const env=environment();await flush()
 assert.equal(env.calls.length,1)
 const url=new URL(env.calls[0].url)
 assert.equal(url.origin,'https://erp.example')
 assert.equal(url.pathname,'/prod-api/sop/weekly-inventory/proxy/files')
 assert.equal(url.searchParams.has('erp_session'),false)
 assert.equal(env.calls[0].options.credentials,'same-origin')
 assert.equal(url.searchParams.get('page'),'1')
 assert.equal(env.elements.get('next').disabled,true)
})

test('refresh without URL session still uses authenticated cookie requests',async()=>{
 const env=environment('');await flush()
 assert.equal(env.calls.length,1)
 assert.equal(new URL(env.calls[0].url).searchParams.has('erp_session'),false)
 assert.equal(env.calls[0].options.credentials,'same-origin')
 assert.equal(env.elements.get('generate').disabled,false)
})

test('manual generation posts one snapshot-only command, never source dates',async()=>{
 const env=environment();await flush()
 await env.elements.get('generate').onclick()
 const requests=env.calls.filter(c=>c.options.method==='POST')
 assert.equal(requests.length,1)
 assert.equal(new URL(requests[0].url).pathname,'/prod-api/sop/weekly-inventory/proxy/run')
 assert.equal(requests[0].options.body,undefined)
 assert.equal(requests[0].options.headers['X-Weekly-Request'],'1')
 assert.match(env.elements.get('snapshotInfo').textContent,/2026-09-10/)
})

test('no successful snapshot disables generation without posting',async()=>{
 const env=environment('token',null);await flush()
 assert.equal(env.elements.get('generate').disabled,true)
 await env.elements.get('generate').onclick()
 assert.equal(env.calls.filter(c=>c.options.method==='POST').length,0)
 assert.match(env.elements.get('snapshotInfo').textContent,/暂无成功快照/)
})
