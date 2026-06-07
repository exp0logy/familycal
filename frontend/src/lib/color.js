// ─────────────────────────────────────────────────────────────────────────────
// Color utilities used by the design system and profile/event rendering.
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Parse a hex color string (3 or 6 digits) into { r, g, b } 0-255.
 * Returns null if the string is not a valid hex color.
 *
 * @param {string} hex  e.g. "#6366f1" or "#f1f"
 * @returns {{ r: number, g: number, b: number }|null}
 */
export function parseHex(hex) {
  if (!hex) return null;
  const s = hex.startsWith('#') ? hex.slice(1) : hex;
  if (s.length === 3) {
    const r = parseInt(s[0] + s[0], 16);
    const g = parseInt(s[1] + s[1], 16);
    const b = parseInt(s[2] + s[2], 16);
    if (isNaN(r) || isNaN(g) || isNaN(b)) return null;
    return { r, g, b };
  }
  if (s.length === 6) {
    const r = parseInt(s.slice(0, 2), 16);
    const g = parseInt(s.slice(2, 4), 16);
    const b = parseInt(s.slice(4, 6), 16);
    if (isNaN(r) || isNaN(g) || isNaN(b)) return null;
    return { r, g, b };
  }
  return null;
}

/**
 * Convert { r, g, b } 0-255 to a "#rrggbb" hex string.
 * @param {{ r: number, g: number, b: number }} rgb
 * @returns {string}
 */
export function toHex({ r, g, b }) {
  return '#' + [r, g, b].map((v) => Math.round(v).toString(16).padStart(2, '0')).join('');
}

/**
 * Return a CSS rgba() string from a hex color with a given alpha.
 * Falls back to accent-500 (#6366f1) for null/invalid colors.
 *
 * @param {string|null} hex
 * @param {number}      alpha  0–1
 * @returns {string}
 */
export function hexToRgba(hex, alpha = 1) {
  const rgb = parseHex(hex ?? '#6366f1') ?? parseHex('#6366f1');
  return `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, ${alpha})`;
}

/**
 * Compute the relative luminance of an RGB color (WCAG formula).
 * @param {{ r: number, g: number, b: number }} rgb
 * @returns {number} 0 (black) – 1 (white)
 */
export function luminance({ r, g, b }) {
  const toLinear = (v) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * toLinear(r) + 0.7152 * toLinear(g) + 0.0722 * toLinear(b);
}

/**
 * Return '#fff' or '#000' — whichever has better contrast with the given hex.
 * Useful for rendering text or icons on a colored background.
 *
 * @param {string|null} hex
 * @returns {'#fff'|'#000'}
 */
export function contrastColor(hex) {
  const rgb = parseHex(hex ?? '#6366f1');
  if (!rgb) return '#fff';
  return luminance(rgb) > 0.35 ? '#000' : '#fff';
}

/**
 * Lighten or darken a hex color.
 * @param {string} hex
 * @param {number} amount  Positive = lighten (0–1), negative = darken
 * @returns {string}
 */
export function adjustColor(hex, amount) {
  const rgb = parseHex(hex);
  if (!rgb) return hex;
  const clamp = (v) => Math.max(0, Math.min(255, v));
  return toHex({
    r: clamp(rgb.r + amount * 255),
    g: clamp(rgb.g + amount * 255),
    b: clamp(rgb.b + amount * 255),
  });
}

/**
 * A curated palette of profile/event accent colors.
 * Chosen to look distinct on a dark background.
 */
export const PALETTE = [
  '#6366f1', // indigo
  '#ec4899', // pink
  '#f59e0b', // amber
  '#10b981', // emerald
  '#06b6d4', // cyan
  '#8b5cf6', // violet
  '#ef4444', // red
  '#14b8a6', // teal
  '#f97316', // orange
  '#a3e635', // lime
  '#64748b', // slate
  '#e879f9', // fuchsia
];

/**
 * Pick a palette color deterministically from a string (e.g. a profile name).
 * @param {string} seed
 * @returns {string} hex color
 */
export function colorFromSeed(seed) {
  let hash = 0;
  for (let i = 0; i < seed.length; i++) {
    hash = (hash * 31 + seed.charCodeAt(i)) | 0;
  }
  return PALETTE[Math.abs(hash) % PALETTE.length];
}
