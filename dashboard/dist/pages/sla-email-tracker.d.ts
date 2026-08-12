/**
 * SLA Email Tracker page - TL operational view for shared mailbox backlog.
 */
export declare function renderSlaEmailTracker(): Promise<void>;
declare function resetSlaFilters(): void;
declare function exportSlaWeeklyOwnerCSV(): void;
declare function exportSlaDailyHistoryCSV(): void;
declare function exportSlaOpenEmailsCSV(): void;
declare function exportSlaActionLogCSV(): void;
declare function exportSlaSupplierSummaryCSV(): void;
export declare const slaEmailTrackerWindowBindings: {
    resetSlaFilters: typeof resetSlaFilters;
    exportSlaWeeklyOwnerCSV: typeof exportSlaWeeklyOwnerCSV;
    exportSlaDailyHistoryCSV: typeof exportSlaDailyHistoryCSV;
    exportSlaOpenEmailsCSV: typeof exportSlaOpenEmailsCSV;
    exportSlaActionLogCSV: typeof exportSlaActionLogCSV;
    exportSlaSupplierSummaryCSV: typeof exportSlaSupplierSummaryCSV;
};
export {};
//# sourceMappingURL=sla-email-tracker.d.ts.map