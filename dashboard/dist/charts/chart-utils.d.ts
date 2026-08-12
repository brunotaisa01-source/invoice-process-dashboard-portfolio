/**
 * chart-utils.ts - Shared Chart.js utilities and configuration.
 */
/**
 * Destroy all active Chart.js instances and clear registry.
 * Call before re-rendering charts to prevent memory leaks.
 */
export declare function destroyCharts(): void;
/**
 * Initialize Chart.js global defaults.
 * Sets font family, colors, legend styles, and grid colors.
 */
export declare function initChartDefaults(): void;
/**
 * Get member color from palette by index.
 * @param i - Team member index
 * @returns Hex color string
 */
export declare function getMemberColor(i: number): string;
//# sourceMappingURL=chart-utils.d.ts.map