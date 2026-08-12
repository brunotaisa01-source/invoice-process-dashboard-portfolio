/**
 * global-filters.ts - Global filter management (sidebar filters for Overview/Trends).
 */
/**
 * Remove legacy week shortcut controls when older generated HTML still has them.
 */
export declare function repopulateWeekSelector(): void;
/**
 * Initialize the reporting date range controls from dashboard data.
 */
export declare function initializeDateRangeControls(): void;
/**
 * Populate all filter dropdowns (team members, countries, document types).
 * Called once on init.
 */
export declare function populateFilters(): void;
/**
 * Bind event listeners to filter controls.
 */
export declare function bindFilters(): void;
/**
 * Update member card visual states based on filterOwner.
 * Applies 'mc-selected' or 'mc-dimmed' classes.
 */
export declare function updateMemberCardStates(): void;
/**
 * Handle global type filter change (Manual/CSV/Envoy checkboxes).
 * Preserves current week by week_start match.
 */
export declare function onGlobalFilterChange(): Promise<void>;
/**
 * Reset all filters to default state.
 */
export declare function resetAllFilters(): void;
export declare const windowBindings: {
    selectMember(name: string): void;
    toggleTypeDropdown(): void;
    toggleTypeOption(el: HTMLInputElement): void;
    resetAllFilters: typeof resetAllFilters;
};
//# sourceMappingURL=global-filters.d.ts.map