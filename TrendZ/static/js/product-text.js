/* Escape untrusted API text before using the legacy page's HTML templates. */
(function (root) {
    function escapeText(value) {
        return String(value).replace(/[&<>"']/g, char => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
        })[char]);
    }
    function safeValues(value) {
        if (value == null) return 'Not verified';
        if (typeof value === 'string') return escapeText(value);
        if (Array.isArray(value)) return value.map(safeValues);
        if (typeof value === 'object') return Object.fromEntries(
            Object.entries(value).map(([key, item]) => [key, safeValues(item)]));
        return value;
    }
    function sourceURL(value) {
        try {
            const url = new URL(value);
            return url.protocol === 'https:' && !url.username && !url.password ? escapeText(url.href) : '#';
        } catch (_) { return '#'; }
    }
    root.ProductText = {escapeText, safeValues, sourceURL};
    if (typeof module !== 'undefined') module.exports = root.ProductText;
})(typeof window === 'undefined' ? globalThis : window);
