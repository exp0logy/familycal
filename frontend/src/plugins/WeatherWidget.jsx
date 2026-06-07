// ─────────────────────────────────────────────────────────────────────────────
// WeatherWidget plugin UI — current conditions + 3-day forecast.
// Registers itself as "WeatherWidget" in the plugin registry on import.
//
// Props (§6): { settings, ws, api, profiles, fullscreen }
//
// Weather data is fetched from /api/plugins/weather/current (plugin router).
// WS event "weather.updated" carries the full snapshot, so we prefer that
// over polling.
// ─────────────────────────────────────────────────────────────────────────────

import React, { useState, useCallback, useEffect } from 'react';
import { registerPlugin } from './registry';
import useWebSocket from '../hooks/useWebSocket';
import Spinner from '../components/Spinner';
import Icon from '../components/Icon';

// ── Weather condition → icon name mapping ─────────────────────────────────────

function conditionIcon(code) {
  // WMO Weather interpretation codes (Open-Meteo)
  if (code === 0)           return 'sun';
  if (code <= 2)            return 'cloud';
  if (code <= 3)            return 'cloud';
  if (code <= 48)           return 'cloud'; // fog
  if (code <= 57)           return 'cloud'; // drizzle
  if (code <= 67)           return 'cloud'; // rain
  if (code <= 77)           return 'cloud'; // snow
  if (code <= 82)           return 'cloud'; // showers
  if (code <= 99)           return 'cloud'; // thunderstorm
  return 'cloud';
}

function conditionLabel(code) {
  if (code === 0)           return 'Clear';
  if (code <= 2)            return 'Partly cloudy';
  if (code <= 3)            return 'Overcast';
  if (code <= 48)           return 'Foggy';
  if (code <= 57)           return 'Drizzle';
  if (code <= 67)           return 'Rain';
  if (code <= 77)           return 'Snow';
  if (code <= 82)           return 'Showers';
  if (code <= 99)           return 'Thunderstorm';
  return 'Unknown';
}

// ── Forecast day component ─────────────────────────────────────────────────────

const ForecastDay = ({ day }) => {
  const date = new Date(day.date);
  const label = date.toLocaleDateString(undefined, { weekday: 'short' });
  return (
    <div className="flex flex-col items-center gap-1 flex-1 min-w-0">
      <span className="text-caption text-text-muted uppercase tracking-wide">{label}</span>
      <Icon name={conditionIcon(day.weather_code)} className="w-5 h-5 text-text-secondary" />
      <div className="flex gap-1 text-body-sm">
        {/* Backend sends temp_max / temp_min (not temperature_max/min) */}
        <span className="text-text-primary font-medium">{Math.round(day.temp_max)}°</span>
        <span className="text-text-muted">{Math.round(day.temp_min)}°</span>
      </div>
    </div>
  );
};

// ── Main component ─────────────────────────────────────────────────────────────

const WeatherWidget = ({ settings, api, fullscreen }) => {
  const units = settings?.units ?? 'metric';
  const unitLabel = units === 'imperial' ? '°F' : '°C';

  const [weather, setWeather]   = useState(null);
  const [fetchError, setFetchError] = useState(false);

  // Fetch the live weather snapshot via ApiClient so VITE_API_BASE is honoured
  const fetchWeather = useCallback(async () => {
    try {
      const data = await api.getPluginData('weather', 'current');
      setWeather(data);
      setFetchError(false);
    } catch {
      // Weather endpoint unavailable — degrade gracefully, don't crash
      setFetchError(true);
    }
  }, [api]);

  useEffect(() => { fetchWeather(); }, [fetchWeather]);

  // Live updates from WS
  useWebSocket('weather.updated', useCallback((envelope) => {
    if (envelope?.payload) setWeather(envelope.payload);
  }, []));

  if (!weather) {
    return (
      <div className="flex items-center gap-3 px-5 py-4">
        {fetchError ? (
          <>
            <Icon name="cloud" className="w-6 h-6 text-text-muted" />
            <span className="text-body-sm text-text-muted">Weather unavailable</span>
          </>
        ) : (
          <Spinner size="sm" />
        )}
      </div>
    );
  }

  const current = weather.current ?? {};
  // Canonical shape (team-lead locked): weather.daily holds the forecast array
  const forecast = weather.daily ?? [];
  // weather snapshot includes location directly; no need for a separate settings fetch
  const location = weather.location ?? '';

  return (
    <div className={`flex flex-col gap-3 ${fullscreen ? 'px-6 py-5' : 'px-5 py-4'}`}>
      {/* Current conditions row */}
      <div className="flex items-center gap-4">
        <Icon name={conditionIcon(current.weather_code)} className="w-10 h-10 text-info flex-shrink-0" />
        <div className="min-w-0">
          <div className="flex items-baseline gap-2">
            <span className="text-title-xl font-bold text-text-primary">
              {/* Canonical field is current.temp (team-lead locked spec) */}
              {current.temp !== undefined ? `${Math.round(current.temp)}${unitLabel}` : '—'}
            </span>
            {/* Backend sends feels_like (not apparent_temperature) */}
            {current.feels_like !== undefined && (
              <span className="text-body-sm text-text-muted">
                Feels {Math.round(current.feels_like)}{unitLabel}
              </span>
            )}
          </div>
          <p className="text-body-sm text-text-secondary">
            {conditionLabel(current.weather_code)}
            {location ? ` · ${location}` : ''}
          </p>
        </div>
        {/* Wind speed */}
        {current.wind_speed !== undefined && (
          <div className="ml-auto text-right flex-shrink-0">
            <p className="text-body-sm text-text-muted leading-tight">Wind</p>
            <p className="text-body text-text-secondary font-medium">
              {Math.round(current.wind_speed)} {units === 'imperial' ? 'mph' : 'km/h'}
            </p>
          </div>
        )}
      </div>

      {/* 3-day forecast */}
      {forecast.length > 0 && (
        <div className="flex items-center gap-2 pt-2 border-t border-surface-4/40">
          {forecast.slice(0, 4).map((day, i) => (
            <ForecastDay key={i} day={day} />
          ))}
        </div>
      )}
    </div>
  );
};

// ── Register in global plugin registry ────────────────────────────────────────
registerPlugin('WeatherWidget', { component: WeatherWidget });

export default WeatherWidget;
