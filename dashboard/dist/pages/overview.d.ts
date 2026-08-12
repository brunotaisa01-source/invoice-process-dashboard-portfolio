/**
 * overview.ts - Overview page rendering (KPIs, member cards, charts, daily table).
 */
import type { FilteredWeek, FilteredMemberDay } from '../types/filtered';
/** Filtered week data with computed aggregations */
interface ProcessedWeekData {
    week: FilteredWeek;
    members: string[];
    dates: string[];
    totals: Record<string, FilteredMemberDay>;
    dailyData: Record<string, Record<string, number>>;
    target: number;
    workingDays: number;
    weekTarget: number;
}
/**
 * Get filtered week data respecting all active filters.
 * @param weekIdx - Week index (defaults to currentWeekIdx)
 * @returns Processed week data or null if not available
 */
export declare function getFilteredWeek(weekIdx?: number): Promise<ProcessedWeekData | null>;
/**
 * Main overview page renderer.
 * Loads week data and renders all components.
 */
export declare function loadWeek(): Promise<void>;
export {};
//# sourceMappingURL=overview.d.ts.map