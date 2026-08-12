/**
 * data-merge.ts - Utilities for merging and aggregating week data.
 */
import type { FilteredWeek } from '../types/filtered';
/**
 * Calculate total credit note count from document type breakdown.
 * @param byDocType - Document type breakdown (e.g., { KG: 5, ST: 2, ... })
 * @returns Total count of credit note types (KG, ST, 1R)
 */
export declare function getCreditNoteCount(byDocType: Record<string, number>): number;
/**
 * Merge two week data objects by summing all metrics.
 * Used to combine manual + CSV + Envoy data based on active type filters.
 *
 * @param w1 - First week data
 * @param w2 - Second week data
 * @returns Merged week data
 */
export declare function mergeWeekData(w1: FilteredWeek, w2: FilteredWeek): FilteredWeek;
//# sourceMappingURL=data-merge.d.ts.map