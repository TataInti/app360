import { test, expect } from '@playwright/test'

test('homepage loads', async ({ page }) => {
  await page.goto('/')
  await expect(page).toHaveTitle(/ 360/)
})

test('navigation works', async ({ page }) => {
  await page.goto('/')
  await page.click('text=Dashboard Operativo')
  await expect(page).toHaveURL(/.*dashboard/)
})

test('sidebar navigation', async ({ page }) => {
  await page.goto('/')
  await expect(page.locator('text=360')).toBeVisible()
  await expect(page.locator('text=Paneles Estratégicos')).toBeVisible()
})