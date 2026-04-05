const { test, expect } = require('@playwright/test');

test.use({
  browserName: 'chromium',
  headless: true,
  viewport: { width: 1440, height: 1100 },
  launchOptions: {
    executablePath: '/usr/bin/google-chrome',
  },
});

test('farm command page harvest button click smoke', async ({ page }) => {
  test.setTimeout(180_000);

  await page.goto('http://127.0.0.1:5173/', {
    waitUntil: 'networkidle',
    timeout: 180_000,
  });

  const plantAssets = page.locator('.robot-facility-map__asset--plant');
  await expect(plantAssets.first()).toBeVisible({ timeout: 180_000 });

  const harvestButtonBeforeOpen = page.getByRole('button', { name: '수확하기' });
  await expect(harvestButtonBeforeOpen).toHaveCount(0);

  await plantAssets.first().click();

  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible({ timeout: 30_000 });
  await expect(dialog.getByRole('button', { name: '수확하기', exact: true })).toBeVisible();
  await dialog.getByRole('button', { name: '수확하기', exact: true }).click();

  await expect(
    dialog.getByRole('button', { name: /수확 준비중|요청 전송 중|접근|자세 보정|집기|적재|중단/ }),
  ).toBeVisible({ timeout: 30_000 });
});
