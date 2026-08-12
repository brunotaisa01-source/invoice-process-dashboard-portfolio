/**
 * detail-filters.ts - Detail page filter management and state.
 */
export declare let detailPage: number;
export declare let detailPerPage: number;
export declare let detailSort: {
    col: string;
    dir: "asc" | "desc";
};
export declare let detailFilterText: string;
export declare let detailFilterDateFrom: string;
export declare let detailFilterDateTo: string;
export declare let detailFilterMember: string;
export declare let detailFilterCountry: string;
export declare let detailActiveTypes: Set<"manual" | "csv" | "envoy">;
export declare let detailFilterDocTypes: Set<string>;
export declare let detailFilterBlocks: Set<string>;
export declare let detailFilterDuplicates: boolean;
export declare function setDetailPage(page: number): void;
export declare function setDetailPerPage(perPage: number): void;
export declare function setDetailSort(col: string, dir: 'asc' | 'desc'): void;
export declare function setDetailFilterText(text: string): void;
export declare function setDetailFilterDateFrom(date: string): void;
export declare function setDetailFilterDateTo(date: string): void;
export declare function setDetailFilterMember(member: string): void;
export declare function setDetailFilterCountry(country: string): void;
export declare function setDetailActiveTypes(types: Set<'manual' | 'csv' | 'envoy'>): void;
export declare function setDetailFilterDocTypes(types: Set<string>): void;
export declare function setDetailFilterBlocks(blocks: Set<string>): void;
export declare function setDetailFilterDuplicates(enabled: boolean): void;
/**
 * Build document type multi-select dropdown for Detail page.
 */
export declare function buildDtDocTypeDropdown(): void;
/**
 * Build payment block multi-select dropdown.
 * Reads unique values from decompressed invoices.
 */
export declare function buildBlockDropdown(): Promise<void>;
/**
 * Update doc type button label based on selection.
 */
export declare function updateDtDocTypeBtnLabel(): void;
/**
 * Update payment block button label based on selection.
 */
export declare function updateBlockBtnLabel(): void;
/**
 * Update detail type filter button label.
 */
export declare function updateDtTypeBtnLabel(): void;
/**
 * Update member navigation UI in detail page.
 */
export declare function updateDetailMemberNavUI(): void;
export declare const detailWindowBindings: {
    toggleDtDocTypeDropdown(): void;
    toggleDtDocTypeOption(el: HTMLInputElement): Promise<void>;
    clearDtDocTypeFilter(): Promise<void>;
    toggleBlockDropdown(): void;
    toggleBlockOption(el: HTMLInputElement): Promise<void>;
    clearBlockFilter(): Promise<void>;
    toggleDtTypeDropdown(): void;
    toggleDtTypeOption(el: HTMLInputElement): Promise<void>;
};
//# sourceMappingURL=detail-filters.d.ts.map