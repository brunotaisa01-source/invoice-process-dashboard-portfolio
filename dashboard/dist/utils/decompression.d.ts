/**
 * decompression.ts - Decompression utilities for compressed data blobs.
 */
import type { WeekData, Invoice } from '../types/dashboard';
/**
 * Decompress a base64-encoded deflate blob.
 * Tries native DecompressionStream first, falls back to pako.
 *
 * @param b64 - Base64-encoded deflate data
 * @returns Parsed JSON object
 */
export declare function decompressBlob(b64: string): Promise<any>;
/**
 * Get decompressed week data from cache or decompress from blob.
 * Implements LRU caching (keeps last 6 weeks).
 *
 * @param key - Week cache key (e.g., "manual_2024-01-05")
 * @returns Decompressed week data or null if not found
 */
export declare function getWeekBlob(key: string): Promise<WeekData | null>;
/**
 * Get decompressed invoices data (cached globally).
 * @returns Array of all invoices
 */
export declare function getInvoices(): Promise<Invoice[]>;
//# sourceMappingURL=decompression.d.ts.map