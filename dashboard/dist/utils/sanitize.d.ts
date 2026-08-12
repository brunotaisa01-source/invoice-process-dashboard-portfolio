/**
 * sanitize.ts - Shared XSS protection utilities.
 *
 * All user-controlled data rendered into HTML must pass through escapeHtml()
 * to prevent Cross-Site Scripting (XSS) attacks. Even "trusted" data like
 * team member names from config can be attack vectors if the config source
 * is compromised or if names contain special characters.
 *
 * Characters escaped: & < > " '
 *
 * @example
 *   escapeHtml('<script>alert(1)</script>')
 *   // Returns: '&lt;script&gt;alert(1)&lt;/script&gt;'
 */
/**
 * Escape HTML special characters to prevent XSS injection.
 *
 * Replaces &, <, >, ", and ' with their HTML entity equivalents.
 * This MUST be applied to any user-controlled string before inserting
 * it into HTML via template literals or innerHTML.
 *
 * @param str - The raw string to escape
 * @returns The HTML-safe escaped string
 */
export declare function escapeHtml(str: string): string;
//# sourceMappingURL=sanitize.d.ts.map