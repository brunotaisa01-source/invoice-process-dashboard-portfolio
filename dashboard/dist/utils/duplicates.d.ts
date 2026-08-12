/**
 * duplicates.ts - Duplicate invoice detection logic.
 */
import type { Invoice } from '../types/dashboard';
/**
 * Detect duplicate invoices based on reference number, work type, and amount matching.
 *
 * Algorithm:
 * 1. Group invoices by reference number, work type, and absolute amount
 * 2. For each group, match positive/negative pairs (potential reversals)
 * 3. Remaining entries: flag exact amount duplicates
 *
 * @param rows - Array of invoice records
 * @returns Set of indices that are duplicates
 */
export declare function getDupIndices(rows: Invoice[]): Set<number>;
//# sourceMappingURL=duplicates.d.ts.map