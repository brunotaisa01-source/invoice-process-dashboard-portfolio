/**
 * formatters.ts - Utility functions for formatting numbers, percentages, and UI elements.
 */
/**
 * Format number with thousand separators (UK locale).
 * @example fmt(1234567) => "1,234,567"
 */
export declare function fmt(n: number): string;
/**
 * Calculate percentage (rounded to integer).
 * @param value - Numerator
 * @param total - Denominator
 * @returns Percentage as integer (0-100)
 */
export declare function pct(value: number, total: number): number;
/**
 * Convert number to ordinal string.
 * @example ordinal(1) => "1st", ordinal(23) => "23rd"
 */
export declare function ordinal(n: number): string;
/**
 * Generate week-over-week comparison badge HTML.
 * @param current - Current period value
 * @param previous - Previous period value
 * @returns HTML string with styled badge
 */
export declare function wowBadge(current: number, previous: number | null | undefined): string;
//# sourceMappingURL=formatters.d.ts.map