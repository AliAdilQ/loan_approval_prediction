/** Capture the running local application and exercise desktop/mobile flows.
 * Optional development tool: npm install --prefix .verification playwright
 * Then set NODE_PATH=.verification/node_modules and run this script.
 */
const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');

const baseURL = process.env.SCREENSHOT_BASE_URL || 'http://127.0.0.1:8000';
assert(['localhost', '127.0.0.1'].includes(new URL(baseURL).hostname), 'Capture only a local demo instance.');
const screenshotDirectory = path.join(__dirname, '..', 'screenshots');
fs.mkdirSync(screenshotDirectory, { recursive: true });

const applicant = {
  applicant_name: 'Alex Morgan', email: 'screenshot-approved@example.com',
  gender: 'Female', married: 'Yes', dependents: '0', education: 'Graduate', self_employed: 'No',
  property_area: 'Urban', applicant_income: '6500', coapplicant_income: '1800', loan_amount: '120000',
  loan_amount_term: '360', credit_history: '1',
};

async function capture(page, filename) {
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({ path: path.join(screenshotDirectory, filename), fullPage: true, animations: 'disabled' });
}

async function assertNoOverflow(page) {
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), `Horizontal overflow on ${page.url()}`);
}

async function submitApplication(page, values) {
  await page.goto(`${baseURL}/predict/`, { waitUntil: 'networkidle' });
  for (const [name, value] of Object.entries(values)) {
    const field = page.locator(`[name="${name}"]`);
    if (await field.evaluate(element => element.tagName === 'SELECT')) await field.selectOption(value);
    else await field.fill(value);
  }
  await Promise.all([page.waitForURL('**/result/**'), page.getByRole('button', { name: 'Generate prediction' }).click()]);
  await page.waitForLoadState('networkidle');
  assert(await page.getByText('Application saved successfully').isVisible());
  return page.url();
}

(async () => {
  const launchOptions = { headless: true };
  if (process.env.PLAYWRIGHT_EXECUTABLE_PATH) launchOptions.executablePath = process.env.PLAYWRIGHT_EXECUTABLE_PATH;
  const browser = await chromium.launch(launchOptions);
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce' });
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('response', response => { if (response.url().includes('/static/') && response.status() >= 400) errors.push(`Static asset failed: ${response.url()}`); });

    await page.goto(baseURL, { waitUntil: 'networkidle' });
    await assertNoOverflow(page);
    assert.equal(await page.locator('.hero-section').count(), 1);
    assert.equal(await page.locator('.feature-card').count(), 4);
    assert.notEqual(await page.locator('.hero-section').evaluate(element => getComputedStyle(element).backgroundColor), 'rgba(0, 0, 0, 0)');
    await capture(page, 'home.png');
    await page.getByRole('link', { name: 'Check Loan Eligibility', exact: true }).click();
    await page.waitForLoadState('networkidle');
    await assertNoOverflow(page);
    assert.equal(await page.locator('.form-control, .form-select').count(), 13);
    await capture(page, 'prediction-form.png');
    await page.getByRole('button', { name: 'Generate prediction' }).click();
    assert.equal(new URL(page.url()).pathname, '/predict/');
    assert(await page.locator('[name="applicant_name"]').evaluate(element => !element.checkValidity()));

    const approvedURL = await submitApplication(page, applicant);
    assert.match(await page.locator('.result-main h1').textContent(), /Approved/);
    await capture(page, 'approved-result.png');
    const rejectedURL = await submitApplication(page, { ...applicant, applicant_name: 'Jordan Lee', email: 'screenshot-rejected@example.com', credit_history: '0', applicant_income: '1000', coapplicant_income: '0', loan_amount: '300000', loan_amount_term: '60' });
    assert.match(await page.locator('.result-main h1').textContent(), /Rejected/);
    await capture(page, 'rejected-result.png');

    const otherContext = await browser.newContext();
    const otherPage = await otherContext.newPage();
    assert.equal((await otherPage.goto(approvedURL)).status(), 404);
    await otherContext.close();

    await page.goto(`${baseURL}/admin/login/?next=/admin/`, { waitUntil: 'networkidle' });
    await page.locator('[name="username"]').fill(process.env.DEMO_ADMIN_USERNAME || 'admin');
    await page.locator('[name="password"]').fill(process.env.DEMO_ADMIN_PASSWORD || 'Admin@12345');
    await Promise.all([page.waitForURL(`${baseURL}/admin/`), page.getByRole('button', { name: 'Log in' }).click()]);
    await page.waitForLoadState('networkidle');
    await capture(page, 'admin-dashboard.png');
    await page.goto(`${baseURL}/admin/predictor/loanapplication/`, { waitUntil: 'networkidle' });
    assert(await page.getByRole('link', { name: 'Alex Morgan', exact: true }).first().isVisible());
    await capture(page, 'applications-list.png');
    await page.goto(`${baseURL}/admin/predictor/loanapplication/?prediction__exact=Rejected&property_area__exact=Urban`, { waitUntil: 'networkidle' });
    assert((await page.locator('#result_list tbody tr').count()) > 0);
    for (const value of await page.locator('.field-prediction').allTextContents()) assert.equal(value, 'Rejected');
    for (const value of await page.locator('.field-property_area').allTextContents()) assert.equal(value, 'Urban');
    await page.goto(`${baseURL}/dashboard/`, { waitUntil: 'networkidle' });
    await capture(page, 'dashboard.png');
    await page.getByRole('textbox', { name: 'Search applications' }).fill('Alex');
    await page.getByRole('button', { name: 'Filter', exact: true }).click();
    for (const name of await page.locator('tbody td:first-child strong').allTextContents()) assert.match(name, /Alex/);

    for (const width of [768, 390]) {
      await page.setViewportSize({ width, height: 844 });
      for (const route of ['/', '/predict/', '/about/', '/dashboard/', new URL(rejectedURL).pathname]) {
        await page.goto(`${baseURL}${route}`, { waitUntil: 'networkidle' });
        await assertNoOverflow(page);
      }
      await page.goto(baseURL, { waitUntil: 'networkidle' });
      await page.getByRole('button', { name: 'Toggle navigation' }).click();
      await page.getByRole('link', { name: 'Loan Prediction', exact: true }).click();
      await page.waitForURL('**/predict/');
      assert(await page.locator('[name="loan_amount"]').isVisible());
      if (width === 390) {
        await page.goto(baseURL, { waitUntil: 'networkidle' });
        await capture(page, 'home-mobile.png');
      }
    }
    assert.deepEqual(errors, [], 'Browser/asset errors');
    console.log(JSON.stringify({ screenshots: fs.readdirSync(screenshotDirectory).filter(name => name.endsWith('.png')), responsiveWidths: [1440, 768, 390], verified: ['real approved/rejected inference', 'form validation', 'session privacy', 'admin login', 'admin filters', 'dashboard search', 'mobile navigation', 'static assets', 'no JavaScript errors', 'no horizontal overflow'] }, null, 2));
    await context.close();
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
