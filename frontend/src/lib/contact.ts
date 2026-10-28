/**
 * Where people send removal requests. Set NEXT_PUBLIC_CONTACT_EMAIL in the
 * deployment. Without it the privacy page points to the team instead of
 * showing an address nobody confirmed.
 */
export const CONTACT_EMAIL = (
  process.env.NEXT_PUBLIC_CONTACT_EMAIL ?? ''
).trim()
