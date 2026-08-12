/**
 * overview-charts.ts - Chart rendering for Overview page (weekly bar + doc type doughnut).
 */
import type { FilteredMemberDay } from '../types/filtered';
/** Data shape for overview charts */
interface OverviewChartData {
    members: string[];
    totals: Record<string, FilteredMemberDay>;
    workingDays: number;
    weekTarget: number;
    workingDaysPerMember?: Record<string, number>;
}
/**
 * Render horizontal bar chart showing weekly totals per member.
 * Includes target line and per-member average/day labels.
 *
 * @param f - Filtered week data for chart
 */
export declare function renderWeeklyChart(f: OverviewChartData): void;
/**
 * Render doughnut chart showing document type distribution.
 * @param f - Filtered week data for chart
 */
export declare function renderDocTypeChart(f: OverviewChartData): void;
export {};
//# sourceMappingURL=overview-charts.d.ts.map