type ClipboardLike = { writeText: (text: string) => Promise<void> }

/** Copies text with the Clipboard API. False when it is missing or refused. */
export async function copyText(
  text: string,
  clipboard: ClipboardLike | undefined = globalThis.navigator?.clipboard,
): Promise<boolean> {
  if (!clipboard) return false
  try {
    await clipboard.writeText(text)
    return true
  } catch {
    return false
  }
}
