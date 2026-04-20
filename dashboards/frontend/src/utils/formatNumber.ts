/**
 * Format a number using Indian numbering system (en-IN locale).
 * e.g. 1,00,000 instead of 100,000
 */
export function formatIndianNumber(n: number): string {
  return n.toLocaleString("en-IN");
}

/**
 * Compact Indian number formatting with Cr / L / K suffixes.
 */
export function formatIndianCompact(n: number): string {
  if (n >= 1_00_00_000) return `${(n / 1_00_00_000).toFixed(1)}Cr`;
  if (n >= 1_00_000) return `${(n / 1_00_000).toFixed(1)}L`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}
