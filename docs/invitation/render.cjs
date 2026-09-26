// Renders each poster HTML in this folder to a 2x PNG in ./png.
//   NODE_PATH=$(npm root -g) node render.cjs            # all posters
//   NODE_PATH=$(npm root -g) node render.cjs invitation.html
// Google Fonts are fetched through Node (route.fetch) so the rendering works
// behind a TLS-intercepting proxy that the headless browser does not trust.
const { chromium } = require('playwright');
const { readdirSync, mkdirSync } = require('node:fs');
const { resolve, basename } = require('node:path');

(async () => {
  const args = process.argv.slice(2);
  const files = args.length ? args : readdirSync(__dirname).filter((f) => f.endsWith('.html'));
  const proxy = process.env.HTTPS_PROXY ? { server: process.env.HTTPS_PROXY } : undefined;
  mkdirSync(resolve(__dirname, 'png'), { recursive: true });

  const browser = await chromium.launch({ proxy });
  for (const file of files) {
    const page = await browser.newPage({ viewport: { width: 1200, height: 1600 }, deviceScaleFactor: 2 });
    await page.route(/^https:\/\/fonts\.(googleapis|gstatic)\.com\//, async (route) => {
      for (let attempt = 1; ; attempt++) {
        try {
          return await route.fulfill({ response: await route.fetch() });
        } catch (err) {
          if (attempt === 4) throw err;
          await new Promise((r) => setTimeout(r, 1000 * 2 ** attempt));
        }
      }
    });
    await page.goto('file://' + resolve(__dirname, file), { waitUntil: 'networkidle' });
    await page.evaluate(() => document.fonts.ready);
    const size = await page.evaluate(() => {
      const r = document.querySelector('.poster').getBoundingClientRect();
      return { width: Math.ceil(r.width), height: Math.ceil(r.height) };
    });
    await page.setViewportSize(size);
    const out = resolve(__dirname, 'png', basename(file, '.html') + '.png');
    await page.locator('.poster').screenshot({ path: out });
    console.log('rendered', basename(out), `${size.width * 2}x${size.height * 2}`);
    await page.close();
  }
  await browser.close();
})();
