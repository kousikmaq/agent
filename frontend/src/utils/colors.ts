/**
 * Deterministic categorical colours for schedule entities (orders / machines).
 *
 * A curated palette of visually distinct, evenly-spread hues gives bars that are
 * easy to tell apart, while a stable hash keeps a given key mapped to the same
 * colour across every chart and legend. When there are more keys than palette
 * entries, later collisions are lightened/darkened so they stay distinguishable.
 */

// Distinct, vivid but harmonious colours that read well on the dark UI.
// Warm and cool hues alternate so neighbouring items stay easy to tell apart.
const PALETTE = [
  "#3b82f6", // blue
  "#f59e0b", // amber
  "#22c55e", // green
  "#ec4899", // pink
  "#06b6d4", // cyan
  "#f97316", // orange
  "#a855f7", // purple
  "#84cc16", // lime
  "#ef4444", // red
  "#14b8a6", // teal
  "#eab308", // yellow
  "#8b5cf6", // violet
  "#f43f5e", // rose
  "#0ea5e9", // sky
  "#d946ef", // fuchsia
  "#10b981", // emerald
];

function hashKey(key: string): number {
  let hash = 0;
  for (let i = 0; i < key.length; i++) {
    hash = (hash * 31 + key.charCodeAt(i)) >>> 0;
  }
  return hash;
}

/** Lighten (positive) or darken (negative) a hex colour by a percentage. */
function shade(hex: string, percent: number): string {
  const n = parseInt(hex.slice(1), 16);
  const clamp = (v: number) => Math.max(0, Math.min(255, v));
  const delta = Math.round(2.55 * percent);
  const r = clamp(((n >> 16) & 0xff) + delta);
  const g = clamp(((n >> 8) & 0xff) + delta);
  const b = clamp((n & 0xff) + delta);
  return `#${((r << 16) | (g << 8) | b).toString(16).padStart(6, "0")}`;
}

/** Stable, visually distinct colour for a key (order id / machine id). */
export function colourFor(key: string): string {
  const hash = hashKey(key);
  const base = PALETTE[hash % PALETTE.length];
  // Vary lightness for keys that wrap past the palette so they stay distinct.
  const cycle = Math.floor(hash / PALETTE.length) % 3;
  if (cycle === 1) return shade(base, 16);
  if (cycle === 2) return shade(base, -16);
  return base;
}
