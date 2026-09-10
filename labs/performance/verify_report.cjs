/* Headless report QA: node verify_report.cjs REPORT OUTPUT [PLAYWRIGHT_MODULE] [CHROMIUM]. */
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const assert = require('node:assert/strict');
const [reportArg, outArg, moduleArg, executableArg] = process.argv.slice(2);
if (!reportArg || !outArg) throw new Error('Expected REPORT and OUTPUT paths');
const { chromium } = require(moduleArg || 'playwright');
const report = path.resolve(reportArg), output = path.resolve(outArg);
fs.mkdirSync(output, { recursive: true });

(async () => {
  const browser = await chromium.launch({ headless: true, ...(executableArg ? { executablePath: executableArg } : {}) });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 });
  const errors = [], externalRequests = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => { if (/^https?:/.test(request.url())) externalRequests.push(request.url()); });
  if (report.endsWith('.svg')) {
    const source = fs.readFileSync(report, 'utf8');
    await page.setContent('<style>body{margin:0;background:#fff}svg{display:block;width:100%;height:auto}</style>' + source.slice(source.indexOf('<svg')));
    await page.screenshot({ path: path.join(output, 'artifact.png'), fullPage: true });
    await browser.close();
    console.log('Rendered SVG in an isolated headless browser');
    return;
  }
  await page.goto(pathToFileURL(report).href);
  await page.waitForSelector('#observations tbody tr');
  assert.equal(await page.locator('h1').count(), 1);
  assert.equal(await page.locator('figure').count(), 11);
  assert.equal(await page.locator('figure svg').count(), 11);
  assert.ok((await page.locator('#validation-results').innerText()).includes('1,801 tests passed'));
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  const missing = await page.evaluate(() => [...document.querySelectorAll('a[href^="#"]')].filter(a => !document.querySelector(a.getAttribute('href'))).map(a => a.getAttribute('href')));
  assert.deepEqual(missing, []);
  const localLinks = await page.locator('a[href]').evaluateAll(anchors => anchors.map(a => a.getAttribute('href')).filter(h => h && !/^(https?:|#|blob:)/.test(h)));
  for (const href of localLinks) assert.ok(fs.existsSync(path.resolve(path.dirname(report), href)), `Missing link: ${href}`);
  await page.screenshot({ path: path.join(output, 'desktop.png') });
  await page.locator('#fig-completion').screenshot({ path: path.join(output, 'completion-figure.png') });
  await page.locator('#fig-render-tradeoffs').screenshot({ path: path.join(output, 'render-figure.png') });
  await page.selectOption('#suite', 'network');
  await page.selectOption('#metric', 'rx_bytes');
  await page.fill('#filter', 'mysql');
  assert.equal(await page.locator('#observations tbody tr').count(), 16);
  assert.ok((await page.locator('#observations tbody').innerText()).includes('13,439,025'));
  const downloading = page.waitForEvent('download');
  await page.click('#export');
  const downloaded = await downloading;
  await downloaded.saveAs(path.join(output, 'filtered-measurements.csv'));
  assert.equal(fs.readFileSync(path.join(output, 'filtered-measurements.csv'), 'utf8').split('\n').length, 17);
  await page.selectOption('#trace-example', 'candidate');
  assert.ok((await page.locator('#trace-status').innerText()).includes('28.91 ms'));
  await page.selectOption('#trace-mode', 'spans');
  assert.equal(await page.locator('#trace-chart rect').count(), 2);
  await page.setInputFiles('#trace-file', path.join(path.dirname(report), 'diagnostics', 'completion-baseline.trace.json'));
  await page.selectOption('#trace-mode', 'delay');
  assert.equal(await page.locator('#trace-example').inputValue(), 'custom');
  assert.ok((await page.locator('#trace-status').innerText()).includes('1629.86 ms'));
  await page.locator('#trace-chart').screenshot({ path: path.join(output, 'trace-viewer.png') });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(pathToFileURL(report).href);
  await page.screenshot({ path: path.join(output, 'mobile.png') });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, 'Mobile page overflows horizontally');
  await page.locator('#explorer h2').scrollIntoViewIfNeeded();
  await page.screenshot({ path: path.join(output, 'mobile-explorer.png') });
  assert.deepEqual(errors, []);
  assert.deepEqual(externalRequests, []);
  const result = { desktop: [1440, 1000], mobile: [390, 844], figures: 11, localLinks: localLinks.length,
    filteredCsvRows: 16, traceUpload: 'passed', horizontalOverflow: false, pageErrors: errors, externalRequests,
    browserVersion: browser.version(), nodeVersion: process.version };
  fs.writeFileSync(path.join(output, 'browser-qa.json'), JSON.stringify(result, null, 2) + '\n');
  console.log(JSON.stringify(result));
  await browser.close();
})().catch(error => { console.error(error); process.exit(1); });
