// @ts-check
import { test, expect } from '@playwright/test';

test.use({
  viewport: { width: 375, height: 812 },
  deviceScaleFactor: 1,
  isMobile: true,
  hasTouch: true,
});

async function expectNoHorizontalOverflow(page) {
  const widths = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    content: document.documentElement.scrollWidth,
  }));
  expect(widths.content).toBeLessThanOrEqual(widths.viewport);
}

async function expectMobileLayout(...pages) {
  for (const width of [320, 375]) {
    await Promise.all(
      pages.map((page) => page.setViewportSize({ width, height: 812 })),
    );
    for (const page of pages) {
      await expectNoHorizontalOverflow(page);
      if (width < 380) {
        await expect(page.locator('.brand-tagline')).toBeHidden();
      }
    }
  }
}

async function expectTouchTarget(locator) {
  const bounds = await locator.boundingBox();
  if (!bounds) {
    throw new Error('Expected the mobile touch target to be visible.');
  }
  expect(bounds.height).toBeGreaterThanOrEqual(44);
}

async function attachMobileScreenshot(testInfo, page, name) {
  await testInfo.attach(name, {
    body: await page.screenshot({ fullPage: true }),
    contentType: 'image/png',
  });
}

test(
  'mobile match flow stays usable and supports multiple coach questions',
  async ({ page, browser }, testInfo) => {
    const guestContext = await browser.newContext({
      viewport: { width: 375, height: 812 },
      deviceScaleFactor: 1,
      isMobile: true,
      hasTouch: true,
    });
    const guest = await guestContext.newPage();

    try {
      await page.goto('/');
      await expect(page).toHaveTitle('Quiz Club / Start a match');
      await expectMobileLayout(page);
      await attachMobileScreenshot(testInfo, page, 'home-mobile');
      await expectTouchTarget(page.locator('.brand-mark'));
      const playerInputFontSize = await page
        .locator('#player-name')
        .evaluate((input) => Number.parseFloat(getComputedStyle(input).fontSize));
      expect(playerInputFontSize).toBeGreaterThanOrEqual(16);

      await page.locator('#player-name').fill('Playwright Host');
      await page.getByRole('button', { name: 'Create a room' }).click();
      await expect(page).toHaveURL(/\/game$/);

      const inviteLink = await page.locator('#invite-link').inputValue();
      await guest.goto(inviteLink);
      await guest.locator('#player-name').fill('Playwright Guest');
      await guest.getByRole('button', { name: 'Join the room' }).click();
      await expect(guest).toHaveURL(/\/game$/);
      await expectMobileLayout(page, guest);
      await expectTouchTarget(guest.getByRole('button', { name: 'I’m ready' }));
      await expectTouchTarget(page.getByRole('button', { name: 'Send message' }));
      const chatInputFontSize = await page
        .locator('#chat-input')
        .evaluate((input) => Number.parseFloat(getComputedStyle(input).fontSize));
      expect(chatInputFontSize).toBeGreaterThanOrEqual(16);

      await page.getByRole('button', { name: 'I’m ready' }).click();
      await guest.getByRole('button', { name: 'I’m ready' }).click();

      await page.locator('#answer-form').waitFor();
      await expectMobileLayout(page, guest);
      await attachMobileScreenshot(testInfo, page, 'question-mobile');
      await expectTouchTarget(page.locator('label.option-card').first());
      await page.locator('label.option-card').first().click();
      await page.locator('#answer-submit').click();
      await guest.locator('#answer-form').waitFor();
      await guest.locator('label.option-card').first().click();
      await guest.locator('#answer-submit').click();

      await expect(page.locator('#coach-name-form')).toBeVisible();
      await expect(page.locator('#coach-question-form')).toBeHidden();
      await expectMobileLayout(page, guest);
      await attachMobileScreenshot(testInfo, page, 'coach-mobile');
      await expectTouchTarget(page.locator('#coach-name-form button'));

      await page.locator('#coach-name-input').fill('Not the host');
      await page.getByRole('button', { name: 'Continue' }).click();
      await expect(page.locator('#coach-status')).toHaveText(
        'Enter the name you used to join this match.',
      );

      await page.locator('#coach-name-input').fill('Playwright Host');
      await page.getByRole('button', { name: 'Continue' }).click();
      await expect(page.locator('#coach-question-form')).toBeVisible();
      const coachInputFontSize = await page
        .locator('#coach-question-input')
        .evaluate((input) => Number.parseFloat(getComputedStyle(input).fontSize));
      expect(coachInputFontSize).toBeGreaterThanOrEqual(16);

      for (const question of [
        'Why did I get this score?',
        'What was the correct answer?',
      ]) {
        await page.locator('#coach-question-input').fill(question);
        await page.locator('#coach-question-submit').click();
        await expect(page.locator('#coach-answers')).toContainText(
          `Test coach reply to: ${question}`,
        );
      }

      await expect(page.locator('#coach-answers')).toContainText(
        'Playwright Host: Why did I get this score?',
      );
      await expect(page.locator('#coach-answers')).toContainText(
        'Playwright Host: What was the correct answer?',
      );

      for (let round = 2; round <= 5; round += 1) {
        await page.getByRole('button', { name: 'Next question' }).click();
        await guest.getByRole('button', { name: 'Next question' }).click();

        await page.locator('#answer-form').waitFor();
        await page.locator('label.option-card').first().click();
        await page.locator('#answer-submit').click();
        await guest.locator('#answer-form').waitFor();
        await guest.locator('label.option-card').first().click();
        await guest.locator('#answer-submit').click();
        await page.locator('#coach-name-form').waitFor();
      }

      await page.getByRole('button', { name: 'Finish match' }).click();
      await guest.getByRole('button', { name: 'Finish match' }).click();
      await expect(page).toHaveURL(/\/results$/);
      await expect(guest).toHaveURL(/\/results$/);
      await expectMobileLayout(page, guest);
      await attachMobileScreenshot(testInfo, page, 'results-mobile');
      await expectTouchTarget(page.locator('a.action-button'));
    } finally {
      await guestContext.close();
    }
  },
);
