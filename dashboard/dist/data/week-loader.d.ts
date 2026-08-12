/**
 * week-loader.ts - Week data loading and date-range merging based on active filters.
 */
import type { WeekIndex } from '../types/dashboard';
import type { FilteredWeek } from '../types/filtered';
/**
 * Get full week data for a specific type and index entry.
 */
export declare function getFullWeek(type: 'manual' | 'csv' | 'envoy', idx_entry: WeekIndex): Promise<FilteredWeek | null>;
/**
 * Get merged week index based on active type filters.
 */
export declare function getWeekIndex(): WeekIndex[];
/**
 * Default reporting period: latest 7 calendar days covered by available row dates.
 */
export declare function getDefaultDateRange(): {
    from: string;
    to: string;
};
export declare function getWeekIndexForRange(from: string, to: string): WeekIndex[];
/**
 * Get full week data merged across all active types.
 */
export declare function getFullWeekMerged(idx: number): Promise<FilteredWeek | null>;
export declare function getFullWeeksMergedForRange(dateFrom: string, dateTo: string): Promise<FilteredWeek[]>;
/**
 * Get data merged across active types and all weeks overlapping a date range.
 * Weekly extraction blobs are displayed by daily entry dates inside the range.
 */
export declare function getFullWeekMergedForRange(dateFrom: string, dateTo: string): Promise<FilteredWeek | null>;
//# sourceMappingURL=week-loader.d.ts.map