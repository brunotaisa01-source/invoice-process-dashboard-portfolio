/**
 * chunk-loader.ts - 3-tier LRU cache and on-demand week data loader.
 *
 * Supports the chunked data architecture:
 *   Tier 1: Core data in DASHBOARD_DATA.compressed_weeks (last 2 weeks, inline)
 *   Tier 2: Trend cube in data_chunks/trend_cube.js (async load)
 *   Tier 3: Historical weeks in data_chunks/week_YYYY-MM-DD.js (on-demand)
 *
 * Falls back to monolithic mode when DASHBOARD_DATA.chunked is not set,
 * providing full backward compatibility.
 */
import type { WeekData, TrendEntry, DashboardData } from '../types/dashboard';
/**
 * Generic LRU (Least Recently Used) cache.
 *
 * Evicts the oldest entry when the cache exceeds maxSize.
 * Uses a Map to maintain insertion order (ES2015+).
 */
export declare class LRUCache<K, V> {
    private cache;
    private readonly maxSize;
    constructor(maxSize: number);
    /**
     * Get a value from the cache. Moves the entry to "most recently used".
     * Returns undefined if the key is not in the cache.
     */
    get(key: K): V | undefined;
    /**
     * Set a value in the cache. Evicts the least recently used entry
     * if the cache is at capacity.
     */
    set(key: K, value: V): void;
    /** Check if a key exists in the cache. */
    has(key: K): boolean;
    /** Remove a key from the cache. */
    delete(key: K): boolean;
    /** Clear all entries from the cache. */
    clear(): void;
    /** Get the current number of entries in the cache. */
    get size(): number;
    /** Get all keys in the cache (oldest to newest). */
    keys(): IterableIterator<K>;
}
/**
 * ChunkLoader - Manages 3-tier on-demand loading and caching of week data.
 *
 * Tier 1 (core): Last 2 weeks stored inline in DASHBOARD_DATA.compressed_weeks.
 * Tier 2 (trend): Trend cube loaded async from data_chunks/trend_cube.js.
 * Tier 3 (historical): Per-week chunks loaded on-demand from data_chunks/week_*.js.
 *
 * Falls back to monolithic mode when chunked=false (all data in compressed_weeks).
 *
 * @example
 * ```typescript
 * const loader = new ChunkLoader(DASHBOARD_DATA, 4);
 * const weekData = loader.getWeek('manual', '2026-03-06');
 * const histData = await loader.loadWeek('manual', '2026-01-09', '2026-01-09');
 * const trend = await loader.loadTrendCube();
 * ```
 */
export declare class ChunkLoader {
    private readonly data;
    private readonly cache;
    private readonly chunkCache;
    private readonly loadingChunks;
    private trendCubeData;
    private trendCubeLoading;
    constructor(dashboardData: DashboardData, maxCacheSize?: number);
    /**
     * Get decompressed week data for a given type and extraction date.
     * Works for Tier 1 (core) data stored inline in DASHBOARD_DATA.
     *
     * @param type - 'manual', 'csv', or 'envoy'
     * @param extractionDate - YYYY-MM-DD format
     * @returns Decompressed WeekData or null if not found inline
     */
    getWeek(type: 'manual' | 'csv' | 'envoy', extractionDate: string): WeekData | null;
    /**
     * Check if a week_start is a historical chunk (Tier 3).
     */
    isChunkedWeek(weekStart: string): boolean;
    /**
     * Load a Tier 3 historical week chunk from data_chunks/.
     * Returns the decompressed WeekData for a specific type within that week.
     *
     * @param type - 'manual', 'csv', or 'envoy'
     * @param weekStart - YYYY-MM-DD format (week_start, not extraction_date)
     * @param extractionDate - used for the cache key
     * @returns Decompressed WeekData or null if not found in chunk
     */
    loadWeek(type: 'manual' | 'csv' | 'envoy', weekStart: string, extractionDate: string): Promise<WeekData | null>;
    /**
     * Load Tier 2 trend cube from data_chunks/trend_cube.js.
     * Returns cached data on subsequent calls.
     *
     * The trend cube is stored as a compressed base64 blob in window.TREND_CUBE.
     */
    loadTrendCube(): Promise<TrendEntry[]>;
    /**
     * Preload specific weeks into the cache (Tier 1 only).
     *
     * Useful for preloading the latest N weeks on page load.
     */
    preload(type: 'manual' | 'csv' | 'envoy', extractionDates: string[]): void;
    /** Get the number of currently cached week entries. */
    get cacheSize(): number;
    /** Clear all caches. */
    clearCache(): void;
    /** Load and cache a Tier 3 chunk file. */
    private _loadChunk;
    /** Actually load a chunk file via <script> tag. */
    private _doLoadChunk;
    /** Actually load the trend cube file. */
    private _doLoadTrendCube;
}
export default ChunkLoader;
//# sourceMappingURL=chunk-loader.d.ts.map