import { test, expect } from '@playwright/test';

test('Simple test to verify Chromium launches', async ({ page }) => {
  console.log('Test started');
  await page.goto('https://www.google.com');
  await page.waitForTimeout(2000);
  console.log('Test completed');
  expect(true).toBe(true);
});
