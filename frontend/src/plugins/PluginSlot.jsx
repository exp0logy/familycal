// ─────────────────────────────────────────────────────────────────────────────
// PluginSlot — renders a named plugin component from the registry, or a
// graceful fallback card if the component is unknown or throws an error.
//
// Imports all built-in plugin modules to ensure they self-register.
// ─────────────────────────────────────────────────────────────────────────────

import React, { Component } from 'react';
import { getPluginComponent } from './registry';
import Icon from '../components/Icon';

// Side-effect imports — each module calls registerPlugin() on load
import './CalendarAgenda';
import './PhotoSlideshow';
import './WeatherWidget';

// ── Error boundary wrapping plugin renders ─────────────────────────────────────

class PluginErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, info) {
    console.error('[PluginSlot] Plugin render error:', error, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
      return (
        <PluginFallback
          name={this.props.name}
          reason={this.state.error?.message ?? 'Render error'}
        />
      );
    }
    return this.props.children;
  }
}

// ── Fallback card shown for unknown / crashed plugins ─────────────────────────

const PluginFallback = ({ name, reason }) => (
  <div className="h-full flex flex-col items-center justify-center gap-3 bg-surface-1 p-6 text-center">
    <Icon name="plugin" className="w-10 h-10 text-surface-5" />
    <div>
      <p className="text-body font-medium text-text-secondary">{name ?? 'Plugin'}</p>
      {reason && (
        <p className="text-body-sm text-text-muted mt-1">{reason}</p>
      )}
    </div>
  </div>
);

// ── PluginSlot ─────────────────────────────────────────────────────────────────

/**
 * @param {{
 *   name: string,              frontend_component name from PluginInfo
 *   settings?: object,
 *   ws?: import('../api/ws').default,
 *   api?: import('../api/client').default,
 *   profiles?: Profile[],
 *   fullscreen?: boolean,
 *   className?: string,
 * }} props
 */
const PluginSlot = ({ name, settings, ws, api, profiles, fullscreen, className = '' }) => {
  const registration = name ? getPluginComponent(name) : null;

  if (!registration) {
    return (
      <div className={`h-full ${className}`}>
        <PluginFallback
          name={name}
          reason={name ? `Component "${name}" is not registered` : 'No component name provided'}
        />
      </div>
    );
  }

  const { component: PluginComponent } = registration;

  return (
    <div className={`h-full ${className}`}>
      <PluginErrorBoundary name={name}>
        <PluginComponent
          settings={settings ?? {}}
          ws={ws}
          api={api}
          profiles={profiles ?? []}
          fullscreen={fullscreen ?? false}
        />
      </PluginErrorBoundary>
    </div>
  );
};

export default PluginSlot;
