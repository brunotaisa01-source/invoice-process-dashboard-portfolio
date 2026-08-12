/**
 * state.ts - Global dashboard state management.
 */
import type { WeekData } from './types/dashboard';
import type { Chart } from 'chart.js';
export type DashboardPage = 'overview' | 'trends' | 'detail' | 'calendar' | 'sla-email-tracker' | 'production';
/** Current active page */
export declare let currentPage: DashboardPage;
/** Active data types (manual, csv, envoy) - global filter */
export declare let activeTypes: Set<"manual" | "csv" | "envoy">;
/** Current week index (0 = most recent) */
export declare let currentWeekIdx: number;
/** Global reporting date range (YYYY-MM-DD). Defaults are initialized from data. */
export declare let dateRangeFrom: string;
export declare let dateRangeTo: string;
/** Filter: selected team member (or 'all') */
export declare let filterOwner: string;
/** Filter: selected country (or 'all') */
export declare let filterCountry: string;
/** Filter: selected document type (or 'all') */
export declare let filterDocType: string;
/** Chart instances registry */
export declare let charts: Record<string, Chart | undefined>;
/** LRU cache for decompressed week data */
export declare const WEEK_CACHE: Map<string, WeekData>;
/** Cache for decompressed invoices data */
export declare let INVOICES_CACHE: any;
/** Dashboard data (loaded via global DASHBOARD_DATA) */
export declare const D: import("./types/dashboard").DashboardData;
export declare function setCurrentPage(page: DashboardPage): void;
export declare function setActiveTypes(types: Set<'manual' | 'csv' | 'envoy'>): void;
export declare function setCurrentWeekIdx(idx: number): void;
export declare function setDateRange(from: string, to: string): void;
export declare function setDateRangeFrom(from: string): void;
export declare function setDateRangeTo(to: string): void;
export declare function setFilterOwner(owner: string): void;
export declare function setFilterCountry(country: string): void;
export declare function setFilterDocType(docType: string): void;
export declare function setCharts(newCharts: Record<string, Chart | undefined>): void;
export declare function setInvoicesCache(data: any): void;
//# sourceMappingURL=state.d.ts.map