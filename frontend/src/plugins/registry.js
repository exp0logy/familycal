// ─────────────────────────────────────────────────────────────────────────────
// Frontend plugin registry — ARCHITECTURE §6.
//
// Built-in plugin UIs register themselves on import.
// The Home page asks the registry for the component named by each enabled
// plugin's `frontend_component`. Unknown component → graceful fallback card.
//
// API:
//   registerPlugin(name, { component, settingsPanel })
//   getPluginComponent(name) → { component, settingsPanel } | null
//   getRegisteredNames()     → string[]
// ─────────────────────────────────────────────────────────────────────────────

/** @type {Map<string, { component: React.ComponentType, settingsPanel: React.ComponentType|null }>} */
const _registry = new Map();

/**
 * Register a frontend plugin component.
 * The `name` must match the `frontend_component` value the backend emits in
 * the PluginInfo response (§3).
 *
 * @param {string} name         e.g. "WeatherWidget", "CalendarAgenda"
 * @param {{ component: React.ComponentType, settingsPanel?: React.ComponentType|null }} descriptor
 */
export function registerPlugin(name, { component, settingsPanel = null }) {
  if (!name || typeof name !== 'string') {
    console.warn('[PluginRegistry] registerPlugin called with invalid name:', name);
    return;
  }
  if (typeof component !== 'function') {
    console.warn('[PluginRegistry] registerPlugin: component must be a React component, got:', typeof component);
    return;
  }
  if (_registry.has(name)) {
    console.warn('[PluginRegistry] Overwriting existing registration for:', name);
  }
  _registry.set(name, { component, settingsPanel });
}

/**
 * Look up a plugin component by its frontend_component name.
 * Returns null if the plugin is not registered (caller should show fallback).
 *
 * @param {string} name
 * @returns {{ component: React.ComponentType, settingsPanel: React.ComponentType|null } | null}
 */
export function getPluginComponent(name) {
  return _registry.get(name) ?? null;
}

/**
 * Return all registered plugin component names.
 * Useful for the Settings panel plugin management UI.
 *
 * @returns {string[]}
 */
export function getRegisteredNames() {
  return Array.from(_registry.keys());
}
