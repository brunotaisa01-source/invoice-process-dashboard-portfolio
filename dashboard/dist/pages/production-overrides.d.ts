/**
 * Production Overrides page - aggregate productivity credit corrections.
 */
export declare function renderProductionOverrides(): Promise<void>;
declare function connectProductionOverridesFolder(): Promise<void>;
declare function saveProductionOverride(): Promise<void>;
declare function deleteProductionOverride(overrideId: string): Promise<void>;
export declare const productionOverridesWindowBindings: {
    connectProductionOverridesFolder: typeof connectProductionOverridesFolder;
    saveProductionOverride: typeof saveProductionOverride;
    deleteProductionOverride: typeof deleteProductionOverride;
};
export {};
//# sourceMappingURL=production-overrides.d.ts.map