import { expect, type Locator } from '@playwright/test'

/**
 * Waits until React has attached its handlers to the element. A click before that is a
 * native form submit that reloads the page, which made the empty-code tests flaky in CI.
 */
export async function hydrated(element: Locator): Promise<void> {
  await expect
    .poll(() =>
      element.evaluate((node) =>
        Object.keys(node).some((key) => key.startsWith('__reactProps')),
      ),
    )
    .toBe(true)
}
