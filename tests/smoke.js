// Run with Playwright available on NODE_PATH, e.g. `node tests/smoke.js`.
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const { pathToFileURL } = require('url');
const { chromium } = require('playwright');
const JSZip = require('jszip');

const root = path.resolve(__dirname, '..');
const names = ['md-folder-combiner', 'pwm-waveform-visualizer', 'image-to-pdf', 'pdf-to-image', 'scientific-calculator', 'csv-extractor'];

(async () => {
  const browser = await chromium.launch({
    executablePath: process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe',
    headless: true
  });
  let pdfBuffer;
  try {
    for (const name of names) {
      const page = await browser.newPage({ acceptDownloads: true });
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.goto(pathToFileURL(path.join(root, 'tools', name, 'index.html')).href);
      assert(await page.locator('h1').count(), `${name}: heading`);
      assert(await page.locator('a[href="../../"]').count(), `${name}: hub navigation`);
      if (name === 'md-folder-combiner') {
        await page.evaluate(() => {
          const transfer = new DataTransfer();
          transfer.items.add(new File(['# Test\n\nBody'], 'sample.md', { type: 'text/markdown' }));
          const input = document.getElementById('folderInput');
          Object.defineProperty(input, 'files', { value: transfer.files, configurable: true });
          input.dispatchEvent(new Event('change'));
        });
        await page.waitForFunction(() => document.getElementById('output').value.includes('Body'));
        assert((await page.locator('#output').inputValue()).includes('Body'));
      }
      if (name === 'pwm-waveform-visualizer') {
        await page.locator('#carrierFrequency').fill('-4');
        await page.locator('#carrierFrequency').dispatchEvent('change');
        assert.strictEqual(await page.locator('#carrierFrequency').inputValue(), '100');
        await page.locator('#resetControls').click();
        assert.strictEqual(await page.locator('#carrierFrequency').inputValue(), '600');
      }
      if (name === 'scientific-calculator') {
        await page.keyboard.press('2');
        await page.keyboard.press('+');
        await page.keyboard.press('3');
        await page.keyboard.press('Enter');
        assert((await page.locator('#histList').innerText()).includes('5'));
        await page.keyboard.press('Escape');
        await page.keyboard.press('1');
        await page.locator('[data-ins="÷"]').click();
        await page.keyboard.press('0');
        await page.keyboard.press('Enter');
        assert((await page.locator('#preview').innerText()).includes('エラー'));
        await page.keyboard.press('Escape');
        await page.locator('[data-ins="tan("]').click();
        await page.keyboard.press('9');
        await page.keyboard.press('0');
        await page.keyboard.press(')');
        await page.keyboard.press('Enter');
        assert((await page.locator('#preview').innerText()).includes('定義されません'));
      }
      if (name === 'image-to-pdf') {
        const chooseImages = page.waitForEvent('filechooser');
        await page.locator('#choose-images').click();
        await (await chooseImages).setFiles({
          name: 'sample.png', mimeType: 'image/png',
          buffer: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScL/nwAAAABJRU5ErkJggg==', 'base64')
        });
        assert((await page.locator('#file-count').innerText()).includes('1 枚'));
        if (await page.evaluate(() => Boolean(window.jspdf?.jsPDF && window.JSZip))) {
          const downloadPromise = page.waitForEvent('download');
          await page.locator('#btn-generate').click();
          const download = await downloadPromise;
          assert(download.suggestedFilename().endsWith('.pdf'));
          assert(fs.statSync(await download.path()).size > 100);
          pdfBuffer = Buffer.from(await page.evaluate(() => Array.from(
            new Uint8Array(new window.jspdf.jsPDF().output('arraybuffer')))));
          const zipPromise = page.waitForEvent('download');
          await page.locator('#btn-compress').click();
          const zipDownload = await zipPromise;
          assert(zipDownload.suggestedFilename().endsWith('.zip'));
          assert(fs.statSync(await zipDownload.path()).size > 100);
          const zip = await JSZip.loadAsync(fs.readFileSync(await zipDownload.path()));
          assert(zip.file('sample.png'), 'PNG original should remain PNG in ZIP');
          await page.evaluate(() => {
            const gif = Uint8Array.from(atob('R0lGODlhAQABAAD/ACwAAAAAAQABAAACADs='), c => c.charCodeAt(0));
            const transfer = new DataTransfer();
            transfer.items.add(new File([gif], 'sample.gif', { type: 'image/gif' }));
            const input = document.getElementById('file-input');
            Object.defineProperty(input, 'files', { value: transfer.files, configurable: true });
            input.dispatchEvent(new Event('change'));
          });
          const gifPdfPromise = page.waitForEvent('download');
          await page.locator('#btn-generate').click();
          assert((await gifPdfPromise).suggestedFilename().endsWith('.pdf'));
        }
      }
      if (name === 'pdf-to-image' && pdfBuffer && await page.evaluate(() => Boolean(window.pdfjsLib && window.JSZip))) {
        const choosePdf = page.waitForEvent('filechooser');
        await page.locator('#drop-zone').click();
        await (await choosePdf).setFiles({ name: 'sample.pdf', mimeType: 'application/pdf', buffer: pdfBuffer });
        await page.waitForFunction(() => document.getElementById('file-meta').textContent.includes('1 ページ'));
        await page.locator('#output-dpi').selectOption('96');
        const downloadPromise = page.waitForEvent('download');
        await page.locator('#btn-convert').click();
        const download = await downloadPromise;
        assert(download.suggestedFilename().endsWith('.png'));
        assert(fs.statSync(await download.path()).size > 100);
        const png = fs.readFileSync(await download.path());
        assert(png.readUInt32BE(16) > 700 && png.readUInt32BE(16) < 1000, '96 DPI output width');
      }
      assert.deepStrictEqual(errors, [], `${name}: browser errors: ${errors.join('; ')}`);
      console.log(`${name}: OK`);
      await page.close();
    }
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
