// Preparado na Fase 7. Executar somente com autorizacao independente da Fase 8.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import http from 'node:http';
import { spawn } from 'node:child_process';

const root = process.cwd();
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const children = [];
const servers = [];
let ws;
const requests = new Map();
const exceptions = [];
const consoleErrors = [];
const denied = [];
let sequence = 0;
function launch(command, args, options = {}) {
  const child = spawn(command, args, { stdio: 'ignore', detached: true, ...options });
  child.on('error', error => { child.launchError = error; });
  children.push(child);
  return child;
}
function terminate(child) {
  if (child?.pid) { try { process.kill(-child.pid, 'SIGTERM'); } catch {} }
}
async function waitFor(fn, message, timeout = 30000) {
  const start = Date.now();
  while (Date.now() - start < timeout) {
    try { const result = await fn(); if (result) return result; } catch {}
    await pause(200);
  }
  throw new Error(message);
}
function command(method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = ++sequence;
    const timer = setTimeout(() => { requests.delete(id); reject(new Error(`CDP timeout: ${method}`)); }, 15000);
    requests.set(id, { resolve, reject, timer });
    ws.send(JSON.stringify({ id, method, params }));
  });
}
async function evaluate(expression) {
  const result = await command('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true });
  assert(!result.exceptionDetails, 'Excecao na avaliacao do navegador');
  return result.result.value;
}
async function navigate(url) {
  await command('Page.navigate', { url });
  await waitFor(() => evaluate(`location.href === ${JSON.stringify(url)} && document.readyState === 'complete'`), 'Navegacao incompleta');
  await pause(1200);
}
function schemas(html) {
  return [...html.matchAll(/<script\b[^>]*type=["']application\/ld\+json["'][^>]*>([\s\S]*?)<\/script>/gi)].map(match => JSON.parse(match[1]));
}
function metadata(html) {
  return {
    title: html.match(/<title[^>]*>([\s\S]*?)<\/title>/i)?.[1],
    description: [...html.matchAll(/<meta\b[^>]*>/gi)].find(m => /name=["']description["']/i.test(m[0]))?.[0],
    canonical: [...html.matchAll(/<link\b[^>]*>/gi)].find(m => /rel=["']canonical["']/i.test(m[0]))?.[0],
  };
}
const domState = `(() => ({
  title:document.title,
  description:document.querySelector('meta[name="description"]')?.content,
  canonical:document.querySelector('link[rel="canonical"]')?.href,
  schema:[...document.querySelectorAll('script[type="application/ld+json"]')].map(e=>JSON.parse(e.textContent)),
  forms:document.forms.length,
  images:[...document.images].filter(e=>/logo|anselmo|mei/i.test(e.alt)).map(e=>({alt:e.alt,src:new URL(e.src).pathname,width:e.naturalWidth,height:e.naturalHeight})),
  text:document.body.innerText
}))()`;

try {
  // Antes da aplicacao: comprovar comunicacao local e bloqueio tambem no navegador.
  const fixture = http.createServer((req, res) => { res.setHeader('Access-Control-Allow-Origin', '*'); res.end('local-only'); });
  await new Promise(resolve => fixture.listen(38881, '127.0.0.1', resolve)); servers.push(fixture);
  const chrome = launch('google-chrome', ['--headless=new', '--disable-background-networking', '--no-first-run', '--no-default-browser-check', '--remote-debugging-address=127.0.0.1', '--remote-debugging-port=9222', `--user-data-dir=${path.join(process.env.HOME, 'chrome')}`, 'about:blank']);
  const targets = await waitFor(async () => {
    if (chrome.launchError || chrome.exitCode !== null) throw new Error('Chrome indisponivel');
    const list = await fetch('http://127.0.0.1:9222/json/list').then(r => r.json());
    return list.find(t => t.type === 'page');
  }, 'Chrome nao iniciou com sandbox padrao; nao desativar protecoes');
  ws = new WebSocket(targets.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { ws.addEventListener('open', resolve, { once: true }); ws.addEventListener('error', reject, { once: true }); });
  ws.addEventListener('message', async event => {
    const data = JSON.parse(event.data);
    if (data.id) {
      const pending = requests.get(data.id);
      if (pending) { clearTimeout(pending.timer); requests.delete(data.id); data.error ? pending.reject(new Error(data.error.message)) : pending.resolve(data.result); }
    }
    if (data.method === 'Runtime.exceptionThrown') exceptions.push(data.params.exceptionDetails.text);
    if (data.method === 'Runtime.consoleAPICalled' && data.params.type === 'error') consoleErrors.push(data.params.args.map(a => a.value ?? a.description).join(' '));
    if (data.method === 'Fetch.requestPaused') {
      const { request, requestId } = data.params;
      const url = new URL(request.url);
      const allowed = url.protocol === 'http:' && url.hostname === '127.0.0.1' && url.port === '3000' && ['GET', 'HEAD'].includes(request.method);
      if (!allowed) denied.push({ origin: url.origin, method: request.method });
      try { await command(allowed ? 'Fetch.continueRequest' : 'Fetch.failRequest', allowed ? { requestId } : { requestId, errorReason: 'BlockedByClient' }); } catch (error) { exceptions.push(error.message); }
    }
  });
  await command('Runtime.enable'); await command('Page.enable');
  await navigate('http://127.0.0.1:38881/');
  assert.equal(await evaluate(`fetch('/').then(r=>r.text())`), 'local-only');
  assert.equal(await evaluate(`fetch('http://192.0.2.1:38881/',{signal:AbortSignal.timeout(2000)}).then(()=>false,()=>true)`), true);
  await command('Fetch.enable', { patterns: [{ urlPattern: '*' }] });
  exceptions.length = 0; consoleErrors.length = 0;
  const results = {};
  for (const variant of ['base', 'proposta']) {
    const app = launch(process.execPath, ['.output/server/index.mjs'], { cwd: path.join(root, 'comparison', variant), env: { ...process.env, PORT: '3000', NITRO_PORT: '3000', HOST: '127.0.0.1', NITRO_HOST: '127.0.0.1' } });
    await waitFor(async () => (await fetch('http://127.0.0.1:3000/')).ok, 'Servidor nao iniciou');
    const pages = {};
    for (const route of ['/', '/politica-de-privacidade']) {
      const response = await fetch(`http://127.0.0.1:3000${route}`);
      assert.equal(response.status, 200);
      const html = await response.text();
      await navigate(`http://127.0.0.1:3000${route}`);
      const dom = await evaluate(domState);
      pages[route] = { metadata: metadata(html), schema: schemas(html), dom };
      assert.deepEqual(dom.schema, pages[route].schema, 'SSR e DOM divergentes');
      assert(pages[route].metadata.title && pages[route].metadata.description && pages[route].metadata.canonical, 'Metadados ausentes');
    }
    await navigate('http://127.0.0.1:3000/');
    // Navegacao pelo link real; sem substituir o roteador da aplicacao.
    assert(await evaluate(`(() => {const a=[...document.querySelectorAll('a')].find(a=>new URL(a.href).pathname==='/politica-de-privacidade' && new URL(a.href).origin===location.origin); if(!a)return false;a.click();return true})()`), 'Link de politica ausente');
    await waitFor(() => evaluate(`location.pathname==='/politica-de-privacidade'`), 'Navegacao client-side falhou');
    await pause(1000);
    assert.deepEqual((await evaluate(domState)).schema, pages['/politica-de-privacidade'].schema, 'Scripts acumulados na navegacao');
    await navigate('http://127.0.0.1:3000/');
    await command('Page.captureScreenshot', { format: 'png' }).then(r => fs.writeFile(`comparison/results/${variant}-home.png`, Buffer.from(r.data, 'base64')));
    const missing = await fetch('http://127.0.0.1:3000/__schema_validation_missing__');
    pages.notFound = { status: missing.status, schema: schemas(await missing.text()) };
    assert.equal(pages.notFound.status, 404); assert.equal(pages.notFound.schema.length, 0);
    results[variant] = pages;
    terminate(app);
    await waitFor(async () => { try { await fetch('http://127.0.0.1:3000/'); return false; } catch { return true; } }, 'Servidor nao encerrou');
  }
  const ids = new Set();
  for (const route of ['/', '/politica-de-privacidade']) {
    const base = results.base[route], proposal = results.proposta[route];
    assert.equal(base.schema.length, 0);
    assert.equal(proposal.schema.length, 1);
    assert.deepEqual(proposal.metadata, base.metadata);
    assert.equal(proposal.dom.forms, base.dom.forms);
    assert.equal(proposal.dom.text, base.dom.text);
    assert.deepEqual(proposal.dom.images, base.dom.images);
    assert(proposal.dom.images.every(i => i.width > 0 && i.height > 0), 'Logo nao carregado');
    const nodes = proposal.schema[0]['@graph'] ?? [proposal.schema[0]];
    const count = type => nodes.filter(n => n['@type'] === type).length;
    assert.equal(count('WebPage'), 1);
    if (route === '/') { assert.equal(nodes.length, 11); assert.equal(count('Organization'), 1); assert.equal(count('WebSite'), 1); assert.equal(count('Service'), 8); }
    else assert.equal(nodes.length, 1);
    for (const node of nodes) { assert(node['@id']); assert(!ids.has(node['@id'])); ids.add(node['@id']); }
  }
  function inspect(value) {
    if (!value || typeof value !== 'object') return;
    if (value['@id']) assert(ids.has(value['@id']), 'Referencia interna inexistente');
    for (const [key, child] of Object.entries(value)) {
      assert(!['address', 'geo', 'review', 'aggregateRating'].includes(key), 'Campo fora do escopo');
      if (key === '@type') assert(!['LocalBusiness', 'AccountingService', 'FAQPage', 'Article', 'BreadcrumbList', 'Offer', 'Review', 'AggregateRating'].includes(child));
      if (key === 'telephone') assert.equal(child, '+5511915470723');
      inspect(child);
    }
  }
  inspect(results.proposta['/'].schema); inspect(results.proposta['/politica-de-privacidade'].schema);
  assert.equal(exceptions.length, 0, `Excecoes no navegador: ${exceptions.join('; ')}`);
  assert.equal(consoleErrors.length, 0, `Erros de console/hidratacao: ${consoleErrors.join('; ')}`);
  await fs.writeFile('comparison/results/runtime.json', JSON.stringify({ results, denied, exceptions, consoleErrors }, null, 2));
  console.log('Comparacao automatizada concluida. Checklist visual/interacoes ainda exige avaliacao; nao equivale a aprovacao de producao.');
} finally {
  ws?.close();
  for (const pending of requests.values()) clearTimeout(pending.timer);
  for (const child of children) terminate(child);
  for (const server of servers) server.close();
}
