// Driver protegido /control. Requer supervisor, isolamento e autorizacao posterior.
import fs from 'node:fs/promises';
import crypto from 'node:crypto';
import http from 'node:http';
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import {StringDecoder} from 'node:string_decoder';

const cases = [];
const failures = [];
const exceptions = [];
const consoleErrors = [];
const networkFailures = new Map();
const requestURLs = new Map();
const pending = new Map();
const variant = process.env.SCHEMA_VARIANT;
let browser, fixture, sequence = 0, session, mainTarget, buffer = '', blockedRequests = 0;
const decoder = new StringDecoder('utf8');
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
function need(condition, code) { if (!condition) throw new Error(code); }
const hash = value => crypto.createHash('sha256').update(JSON.stringify(value)).digest('hex');
const sorted = value => Array.isArray(value) ? value.map(sorted) : value && typeof value === 'object' ? Object.fromEntries(Object.keys(value).sort().map(key => [key, sorted(value[key])])) : value;
function equal(a, b, code) { need(JSON.stringify(sorted(a)) === JSON.stringify(sorted(b)), code); }
function command(method, params = {}, sid = session, timeout = 5000) {
  return new Promise((resolve, reject) => {
    const id = ++sequence;
    const timer = setTimeout(() => { pending.delete(id); reject(new Error('CDP_TIMEOUT')); }, timeout);
    pending.set(id, {resolve, reject, timer});
    browser.stdio[3].write(JSON.stringify({id, method, params, ...(sid ? {sessionId: sid} : {})}) + '\0', error => {
      if (error) { clearTimeout(timer); pending.delete(id); reject(new Error('CDP_PIPE_WRITE')); }
    });
  });
}
function disconnect() {
  for (const item of pending.values()) { clearTimeout(item.timer); item.reject(new Error('CDP_DISCONNECTED')); }
  pending.clear();
}
async function event(data) {
  if (data.id) {
    const item = pending.get(data.id);
    if (item) { clearTimeout(item.timer); pending.delete(data.id); data.error ? item.reject(new Error('CDP_COMMAND_FAILED')) : item.resolve(data.result); }
    return;
  }
  if (data.method === 'Target.attachedToTarget' && data.params.targetInfo.targetId !== mainTarget) {
    failures.push('UNEXPECTED_BROWSER_TARGET');
    await command('Target.closeTarget', {targetId: data.params.targetInfo.targetId}, null);
  }
  if (data.sessionId !== session) return;
  if (data.method === 'Runtime.exceptionThrown') exceptions.push('BROWSER_EXCEPTION');
  if (data.method === 'Runtime.consoleAPICalled' && data.params.type === 'error') consoleErrors.push('BROWSER_CONSOLE_ERROR');
  if (data.method === 'Network.requestWillBeSent') requestURLs.set(data.params.requestId, data.params.request.url);
  if (data.method === 'Network.loadingFailed') networkFailures.set(requestURLs.get(data.params.requestId), data.params.errorText);
  if (data.method === 'Fetch.requestPaused') {
    const {requestId, request} = data.params;
    const url = new URL(request.url);
    const allow = url.protocol === 'http:' && url.hostname === '127.0.0.1' && url.port === '3000' && ['GET', 'HEAD'].includes(request.method);
    if (!allow) blockedRequests++;
    await command(allow ? 'Fetch.continueRequest' : 'Fetch.failRequest', allow ? {requestId} : {requestId, errorReason: 'BlockedByClient'});
  }
}
async function evaluate(expression, timeout = 5000) {
  const result = await command('Runtime.evaluate', {expression, awaitPromise: true, returnByValue: true}, session, timeout);
  need(!result.exceptionDetails, 'EVALUATION_EXCEPTION');
  return result.result.value;
}
async function until(predicate, code, timeout = 15000) {
  const end = Date.now() + timeout;
  while (Date.now() < end) {
    if (await predicate()) return;
    await delay(100);
  }
  throw new Error(code);
}
async function navigate(route) {
  const url = 'http://127.0.0.1:3000' + route;
  const result = await command('Page.navigate', {url});
  need(!result.errorText, 'NAVIGATION_FAILED');
  await until(() => evaluate(`location.href===${JSON.stringify(url)} && document.readyState==='complete' && Boolean(document.body)`), 'PAGE_NOT_READY');
  await evaluate('document.fonts.ready.then(()=>true)');
}
async function click(selector) {
  const position = await evaluate(`(() => {const element=document.querySelector(${JSON.stringify(selector)}); if(!element)return null; element.scrollIntoView({block:'center'}); const r=element.getBoundingClientRect(); if(!r.width||!r.height)return null; const x=r.x+r.width/2,y=r.y+r.height/2; const top=document.elementFromPoint(x,y); return top && (top===element||element.contains(top)) ? {x,y} : null})()`);
  need(position, 'CONTROL_NOT_INTERACTABLE');
  await command('Input.dispatchMouseEvent', {type:'mouseMoved', ...position});
  await command('Input.dispatchMouseEvent', {type:'mousePressed', button:'left', clickCount:1, ...position});
  await command('Input.dispatchMouseEvent', {type:'mouseReleased', button:'left', clickCount:1, ...position});
}
// Parser HTML do navegador, sem regex para metadados ou scripts JSON-LD.
const parseDocument = `(doc => {
  const titles=[...doc.querySelectorAll('title')];
  const descriptions=[...doc.querySelectorAll('meta[name="description"]')];
  const canonicals=[...doc.querySelectorAll('link[rel="canonical"]')];
  if(titles.length!==1||descriptions.length!==1||canonicals.length!==1)throw Error('META_COUNT');
  const metadata={title:titles[0].textContent,description:descriptions[0].content,canonical:canonicals[0].getAttribute('href')};
  if(!metadata.title||!metadata.description||!metadata.canonical)throw Error('META_EMPTY');
  const schema=[...doc.querySelectorAll('script[type="application/ld+json"]')].map(e=>JSON.parse(e.textContent));
  const clone=doc.body.cloneNode(true); clone.querySelectorAll('script,style').forEach(e=>e.remove());
  const forms=[...doc.forms].map(f=>({action:f.getAttribute('action'),method:f.method,fields:[...f.elements].map(e=>({name:e.name,type:e.type,required:e.required}))}));
  return {metadata,schema,text:clone.textContent.replace(/\\s+/g,' ').trim(),forms};
})`;
async function inspectPage(route) {
  const response = await fetch('http://127.0.0.1:3000' + route, {signal:AbortSignal.timeout(5000)});
  need(response.status===200, 'SSR_STATUS');
  const html=await response.text();
  const ssr=await evaluate(`${parseDocument}(new DOMParser().parseFromString(${JSON.stringify(html)},'text/html'))`);
  const dom=await evaluate(`${parseDocument}(document)`);
  equal(ssr.metadata,dom.metadata,'SSR_DOM_METADATA');
  equal(ssr.schema,dom.schema,'SSR_DOM_JSONLD');
  need(new URL(dom.metadata.canonical).origin==='https://www.anselmodiascontador.com.br','CANONICAL_ORIGIN');
  if(variant==='base') need(dom.schema.length===0,'BASE_UNEXPECTED_SCHEMA');
  else {
    need(dom.schema.length===1,'PROPOSAL_SCHEMA_COUNT');
    const expected=JSON.parse(await fs.readFile(route==='/'?'/reference/home.json':'/reference/politica-de-privacidade.json','utf8'));
    const actual=structuredClone(dom.schema[0]);
    if(route==='/') {
      const org=actual['@graph']?.find(node=>node['@type']==='Organization');
      const reference=expected['@graph']?.find(node=>node['@type']==='Organization');
      need(org && reference && typeof org.logo==='string','ORGANIZATION_LOGO_REQUIRED');
      const logo=new URL(org.logo);
      need(logo.origin==='https://www.anselmodiascontador.com.br' && /^\/assets\/logo-anselmo-dias-[A-Za-z0-9_-]+\.webp$/.test(logo.pathname) && !logo.search && !logo.hash,'SCHEMA_LOGO_URL');
      const asset=await fetch('http://127.0.0.1:3000'+logo.pathname,{signal:AbortSignal.timeout(5000)});
      need(asset.ok && (asset.headers.get('content-type')||'').startsWith('image/'),'SCHEMA_LOGO_ASSET');
      org.logo=reference.logo; // Unica normalizacao permitida: nome emitido do mesmo asset.
    }
    equal(actual,expected,'APPROVED_JSONLD_MISMATCH');
  }
  const logos=await evaluate(`Array.from(document.images).filter(e=>e.alt==='Anselmo Dias Contador').filter(e=>{const r=e.getBoundingClientRect();return r.width>0&&r.height>0&&r.bottom>0&&r.top<innerHeight&&r.right>0&&r.left<innerWidth}).map(e=>({path:new URL(e.src).pathname,width:e.naturalWidth,height:e.naturalHeight}))`);
  need(logos.length>0 && logos.every(i=>i.width>0&&i.height>0),'VISIBLE_LOGO_REQUIRED');
  return {metadata:hash(dom.metadata), text:hash(dom.text), forms:hash(dom.forms), logos:hash(logos)};
}
async function hydrationHome() {
  await click('button[aria-label="Abrir menu"]');
  await until(()=>evaluate('Boolean(document.querySelector(\'button[aria-label="Fechar menu"]\'))'),'REACT_HOME_INTERACTION');
  await click('button[aria-label="Fechar menu"]');
  await until(()=>evaluate('Boolean(document.querySelector(\'button[aria-label="Abrir menu"]\'))'),'REACT_HOME_RESET');
  cases.push('home-react-state');
}
async function hydrationPrivacy() {
  const selector='button[aria-controls="card-01-content"]';
  need(await evaluate(`document.querySelector(${JSON.stringify(selector)})?.getAttribute('aria-expanded')==='true'`),'PRIVACY_INITIAL_STATE');
  await click(selector);
  await until(()=>evaluate(`document.querySelector(${JSON.stringify(selector)})?.getAttribute('aria-expanded')==='false'`),'REACT_PRIVACY_INTERACTION');
  await click(selector);
  await until(()=>evaluate(`document.querySelector(${JSON.stringify(selector)})?.getAttribute('aria-expanded')==='true'`),'REACT_PRIVACY_RESET');
  cases.push('privacy-react-state');
}

let result={automated_checks:'failed',manual_review:'pending',cases,comparison:{},diagnostics:[]};
try {
  need(JSON.parse(await fs.readFile('/control/EXECUTION-POLICY.json','utf8')).phase8_authorized===true,'PHASE8_NOT_AUTHORIZED');
  need(process.getuid()===62002 && process.getgid()===62002,'DRIVER_IDENTITY');
  need(['base','proposta'].includes(variant),'DRIVER_VARIANT');
  const status=await fs.readFile('/proc/self/status','utf8');
  need(/^Groups:[ \t]*$/m.test(status),'SUPPLEMENTARY_GROUPS_PRESENT');
  need(['CapInh','CapPrm','CapEff','CapBnd','CapAmb'].every(key=>new RegExp(key+':\\s+0000000000000000').test(status)) && /NoNewPrivs:\s+1/.test(status),'DRIVER_PRIVILEGES');
  fixture=http.createServer((request,response)=>{response.setHeader('Content-Type','text/plain');response.end('schema-local-fixture');});
  fixture.requestTimeout=2000;
  await new Promise((resolve,reject)=>{fixture.once('error',reject);fixture.listen(38881,'127.0.0.1',resolve);});
  browser=spawn('/usr/bin/google-chrome',['--headless=new','--no-first-run','--no-default-browser-check','--disable-background-networking','--remote-debugging-pipe','--user-data-dir=/tmp/browser-home/profile'],{stdio:['ignore','ignore','ignore','pipe','pipe'],env:process.env});
  browser.once('error',()=>{failures.push('CHROME_START_FAILED');disconnect();});
  browser.once('exit',disconnect);
  browser.stdio[4].on('data',chunk=>{
    buffer+=decoder.write(chunk);
    if(buffer.length>8_000_000){failures.push('CDP_FRAME_LIMIT');browser.kill('SIGKILL');return;}
    let index;
    while((index=buffer.indexOf('\0'))!==-1){const message=buffer.slice(0,index);buffer=buffer.slice(index+1);if(message)Promise.resolve().then(()=>event(JSON.parse(message))).catch(()=>failures.push('CDP_EVENT_FAILED'));}
  });
  ({targetId:mainTarget}=await command('Target.createTarget',{url:'about:blank'},null));
  ({sessionId:session}=await command('Target.attachToTarget',{targetId:mainTarget,flatten:true},null));
  await command('Target.setAutoAttach',{autoAttach:true,waitForDebuggerOnStart:true,flatten:true},null);
  await command('Page.enable');await command('Runtime.enable');await command('Network.enable');
  await command('Page.addScriptToEvaluateOnNewDocument',{source:'window.__schemaDocumentIdentity=crypto.randomUUID()'});
  await command('Page.navigate',{url:'http://127.0.0.1:38881/'});
  await until(()=>evaluate(`document.readyState==='complete'&&location.port==='38881'`),'FIXTURE_NOT_READY');
  need(await evaluate(`fetch('/').then(r=>r.text())`)==='schema-local-fixture','BROWSER_LOCAL_FIXTURE');
  const probe='http://192.0.2.1:38881/';
  await evaluate(`fetch(${JSON.stringify(probe)},{signal:AbortSignal.timeout(2000)}).then(()=>false,()=>true)`);
  need(['net::ERR_ADDRESS_UNREACHABLE','net::ERR_NETWORK_UNREACHABLE'].includes(networkFailures.get(probe)),'BROWSER_BLOCK_NOT_PROVEN');
  await command('Fetch.enable',{patterns:[{urlPattern:'*'}]});
  exceptions.length=0;consoleErrors.length=0;networkFailures.clear();
  const resume=once(process.stdin,'data');
  process.stdout.write('READY_FOR_LOCAL_SERVER\n');
  const [instruction]=await Promise.race([resume,new Promise((_,reject)=>setTimeout(()=>reject(new Error('SUPERVISOR_HANDSHAKE_TIMEOUT')),15000))]);
  need(instruction.toString().trim()==='CONTINUE','SUPERVISOR_HANDSHAKE');
  await until(async()=>{try{return(await fetch('http://127.0.0.1:3000/',{signal:AbortSignal.timeout(1000)})).ok;}catch{return false;}},'APP_NOT_READY');
  for(const viewport of [{name:'desktop',width:1280,height:900,mobile:false},{name:'mobile',width:390,height:844,mobile:true}]) {
    await command('Emulation.setDeviceMetricsOverride',{width:viewport.width,height:viewport.height,deviceScaleFactor:1,mobile:viewport.mobile});
    await navigate('/');
    if(viewport.mobile)await hydrationHome();
    result.comparison[viewport.name+'-home']=await inspectPage('/');
    const identity=await evaluate('window.__schemaDocumentIdentity');
    const timeOrigin=await evaluate('performance.timeOrigin');
    need(typeof identity==='string' && identity.length>10,'DOCUMENT_IDENTITY_REQUIRED');
    await click('a[href="/politica-de-privacidade"]');
    await until(()=>evaluate(`location.pathname==='/politica-de-privacidade'&&document.querySelector('button[aria-controls="card-01-content"]')!==null`),'CLIENT_ROUTE_NOT_READY');
    need(await evaluate('window.__schemaDocumentIdentity')===identity && await evaluate('performance.timeOrigin')===timeOrigin,'FULL_RELOAD_NOT_CLIENT_NAVIGATION');
    await hydrationPrivacy();
    result.comparison[viewport.name+'-privacy']=await inspectPage('/politica-de-privacidade');
    const history=await command('Page.getNavigationHistory');
    need(history.currentIndex>0,'HISTORY_ENTRY_REQUIRED');
    await command('Page.navigateToHistoryEntry',{entryId:history.entries[history.currentIndex-1].id});
    await until(()=>evaluate(`location.pathname==='/'`),'CLIENT_HISTORY_FAILED');
    need(await evaluate('window.__schemaDocumentIdentity')===identity,'HISTORY_FULL_RELOAD');
    const capture=await command('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
    await fs.writeFile('/evidence/'+viewport.name+'-home.png',Buffer.from(capture.data,'base64'),{mode:0o600,flag:'wx'});
    cases.push(viewport.name+'-ssr-dom-navigation');
  }
  const missing=await fetch('http://127.0.0.1:3000/__schema_validation_missing__',{signal:AbortSignal.timeout(5000)});
  need(missing.status===404,'NOT_FOUND_STATUS');
  const missingHTML=await missing.text();
  need(await evaluate(`new DOMParser().parseFromString(${JSON.stringify(missingHTML)},'text/html').querySelectorAll('script[type="application/ld+json"]').length`)===0,'NOT_FOUND_SCHEMA');
  need(failures.length===0 && exceptions.length===0 && consoleErrors.length===0,'BROWSER_ERRORS');
  // Falhas de recursos locais nao podem passar como hidratacao aprovada.
  need(![...networkFailures.keys()].some(url=>url?.startsWith('http://127.0.0.1:3000/')),'LOCAL_RESOURCE_FAILED');
  cases.push('approved-jsonld','required-metadata-logo','network-denied-'+blockedRequests);
  result.automated_checks='passed';
} catch(error) {
  const reason=/^[A-Z0-9_]{1,80}$/.test(error?.message||'')?error.message:'DRIVER_CHECK_FAILED';
  failures.push(reason);result.diagnostics.push(reason);
} finally {
  try{await fs.writeFile('/evidence/result.json',JSON.stringify(result),{mode:0o600,flag:'wx'});}catch{failures.push('EVIDENCE_WRITE_FAILED');}
  try{if(browser)await command('Browser.close',{},null,1000);}catch{}
  if(browser && browser.exitCode===null){browser.kill('SIGTERM');await delay(300);if(browser.exitCode===null)browser.kill('SIGKILL');}
  disconnect();fixture?.close();process.stdin.destroy();
}
process.exitCode=result.automated_checks==='passed'&&failures.length===0?0:78;
