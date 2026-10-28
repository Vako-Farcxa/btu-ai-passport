/**
 * BTU education levels and the degree programs under each one.
 *
 * Source (read 2026-10-28), the official BTU website:
 *   Bachelor's: https://btu.edu.ge/en/apply/undergraduate-programs/
 *               https://btu.edu.ge/migheba/sabakalavro-programebi/ (Georgian)
 *   Master's:   https://btu.edu.ge/en/apply/masters-programs/
 *               https://btu.edu.ge/migheba/samagistro-programebi/ (Georgian)
 *   Doctoral:   https://btu.edu.ge/en/apply/doqtorantura/ (Georgian only; the English
 *               names below are translated from it)
 *   Overview:   https://btu.edu.ge/en/stsavla/programebi/
 *
 * The values are written to the Google Sheet, so the spelling follows what the Sheet
 * already uses ("Bachelor's", "Master's", and a plain hyphen in "Information Systems
 * Management - DevOps" where the website has an en dash). Do not "fix" them to the
 * website spelling without updating the Sheet.
 */

export const EDUCATION_LEVELS = ["Bachelor's", "Master's", 'Doctoral'] as const

export type EducationLevel = (typeof EDUCATION_LEVELS)[number]

export const PROGRAMS_BY_LEVEL: Record<EducationLevel, readonly string[]> = {
  "Bachelor's": [
    'Computer Science and Artificial Intelligence',
    'Business Administration (Management)',
    'Business Administration (Finance)',
    'Digital Marketing',
    'Information Technologies',
    'Psychology in the Digital World',
    'Business Administration (English-Taught)',
    'Computer Science and Artificial Intelligence (English-Taught)',
  ],
  "Master's": [
    'Business Administration and Modern Technologies',
    'Information Systems Management - DevOps',
    'International Security and Technologies',
    'Data-Driven Digital Marketing',
    'Business Administration for Executive Managers',
    'Digital Marketing',
  ],
  Doctoral: [
    'Business Administration',
    'Digital Governance and Artificial Intelligence in the Public Sector',
  ],
}

/** Programs offered at a level. An unknown or empty level has none. */
export function programsForLevel(level: string): readonly string[] {
  return EDUCATION_LEVELS.find((item) => item === level)
    ? PROGRAMS_BY_LEVEL[level as EducationLevel]
    : []
}
