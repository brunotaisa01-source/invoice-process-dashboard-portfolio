/**
 * detail.ts - Detail invoice table page with advanced filtering and sorting.
 */
import type { Invoice } from '../types/dashboard';
/**
 * Apply all active filters to invoice list.
 * @returns Filtered and sorted invoice array
 */
export declare function getFilteredInvoices(): Promise<Invoice[]>;
/**
 * Render detail table page with filters and KPIs.
 */
export declare function renderDetailTable(): Promise<void>;
/**
 * Render table rows with pagination (called after filters change).
 */
export declare function renderDetailRows(): Promise<void>;
export declare const detailWindowBindings: {
    sortDetail(col: string): void;
    goToDetailPage(page: number): void;
    searchDetail(value: string): void;
    setDateFrom(value: string): void;
    setDateTo(value: string): void;
    filterByMember(name: string): void;
    setDetailOwner(value: string): void;
    changePerPage(value: string): void;
    toggleDupFilter(): void;
    resetDetailFilters(): void;
    exportDetailCSV(): Promise<void>;
};
//# sourceMappingURL=detail.d.ts.map