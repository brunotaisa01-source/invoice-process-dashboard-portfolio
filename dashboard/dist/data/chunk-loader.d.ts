/**
 * chunk-loader.ts - Dynamic loading of Tier 3 historical week chunks.
 *
 * Loads data_chunks/week_YYYY-MM-DD.js files on demand via <script> tags.
 * Each chunk sets window.WEEK_YYYY_MM_DD with compressed week data for all types.
 * Works with file:// protocol (no fetch/CORS issues).
 */
/**
 * Ensure a week's chunk data is available in D.compressed_weeks.
 *
 * If the key exists in compressed_weeks (core week), returns immediately.
 * If not, loads the corresponding chunk file from data_chunks/.
 *
 * @param key - Week cache key (e.g., "manual_2026-02-13")
 * @returns true if data is now available, false if not
 */
export declare function ensureWeekData(key: string): Promise<boolean>;
//# sourceMappingURL=chunk-loader.d.ts.map