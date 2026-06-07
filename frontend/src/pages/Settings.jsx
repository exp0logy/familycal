// ─────────────────────────────────────────────────────────────────────────────
// Settings page — full configuration panel.
//
// Sections:
//  1. Profiles      — add/edit/delete family member profiles
//  2. Calendar      — calendar source management + OAuth connections + CalDAV
//  3. Photos        — Google Photos OAuth + slideshow interval
//  4. Weather       — location, units
//  5. Screensaver   — idle timeout
//  6. Plugins       — enable/disable plugins
//  7. Display       — layout prefs (future)
//
// Navigation: sidebar on wide screens, tab bar on narrow screens.
// ─────────────────────────────────────────────────────────────────────────────

import React, { useState, useCallback, useEffect } from 'react';
import Button from '../components/Button';
import Card from '../components/Card';
import Toggle from '../components/Toggle';
import TextInput from '../components/TextInput';
import Modal from '../components/Modal';
import ColorPicker from '../components/ColorPicker';
import Spinner from '../components/Spinner';
import Icon from '../components/Icon';
import StatusDot from '../components/StatusDot';
import ApiClient from '../api/client';
import useApi from '../hooks/useApi';
import useSettings from '../hooks/useSettings';
import { hexToRgba, colorFromSeed } from '../lib/color';

// ─────────────────────────────────────────────────────────────────────────────
// Section: Profiles
// ─────────────────────────────────────────────────────────────────────────────

const EMOJI_SUGGESTIONS = ['👨', '👩', '👦', '👧', '🧑', '👶', '🐶', '🐱', '⭐', '🎸', '🏃', '📚'];

const ProfileForm = ({ initial, onSave, onCancel, saving }) => {
  const [name,  setName]  = useState(initial?.name  ?? '');
  const [color, setColor] = useState(initial?.color ?? colorFromSeed(initial?.name ?? 'new'));
  const [emoji, setEmoji] = useState(initial?.emoji ?? '👤');
  const [error, setError] = useState('');

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!name.trim()) { setError('Name is required'); return; }
    onSave({ name: name.trim(), color, emoji });
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      <TextInput
        label="Name"
        value={name}
        onChange={(e) => { setName(e.target.value); setError(''); }}
        placeholder="Family member name"
        required
        autoFocus
        error={error}
      />

      <div>
        <span className="text-body-sm font-medium text-text-secondary block mb-2">Emoji</span>
        <div className="flex flex-wrap gap-2">
          {EMOJI_SUGGESTIONS.map((em) => (
            <button
              key={em}
              type="button"
              onClick={() => setEmoji(em)}
              className={`w-10 h-10 rounded-lg text-xl flex items-center justify-center transition-all duration-[150ms]
                ${emoji === em ? 'bg-accent-500/20 ring-2 ring-accent-500 scale-110' : 'bg-surface-3 hover:bg-surface-4'}`}
            >
              {em}
            </button>
          ))}
        </div>
      </div>

      <ColorPicker label="Colour" value={color} onChange={setColor} />
    </form>
  );
};

const ProfileCard = ({ profile, onEdit, onDelete }) => (
  <div className="flex items-center gap-3 py-3 border-b border-surface-4/40 last:border-0">
    <span
      className="w-10 h-10 rounded-full flex items-center justify-center text-xl flex-shrink-0"
      style={{ backgroundColor: hexToRgba(profile.color, 0.2) }}
      aria-hidden="true"
    >
      {profile.emoji || profile.name.charAt(0)}
    </span>
    <div className="flex-1 min-w-0">
      <p className="text-body font-medium text-text-primary truncate-1">{profile.name}</p>
    </div>
    <div className="flex items-center gap-1">
      <Button
        variant="icon" size="sm"
        onClick={() => onEdit(profile)}
        title={`Edit ${profile.name}`}
        icon={<Icon name="edit" className="w-4 h-4" />}
      />
      <Button
        variant="icon" size="sm"
        onClick={() => onDelete(profile)}
        title={`Delete ${profile.name}`}
        icon={<Icon name="trash" className="w-4 h-4 text-error" />}
      />
    </div>
  </div>
);

const ProfilesSection = () => {
  const fetcher = useCallback(() => ApiClient.getProfiles(), []);
  const { data: profiles, loading, refetch } = useApi(fetcher, []);
  const [modal, setModal]   = useState(null); // null | { mode: 'add'|'edit'|'delete', profile? }
  const [saving, setSaving] = useState(false);

  const handleSave = async (data) => {
    setSaving(true);
    try {
      if (modal.mode === 'add') {
        await ApiClient.createProfile(data);
      } else {
        await ApiClient.updateProfile(modal.profile.id, data);
      }
      refetch();
      setModal(null);
    } catch (e) {
      console.error('Profile save error:', e);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    setSaving(true);
    try {
      await ApiClient.deleteProfile(modal.profile.id);
      refetch();
      setModal(null);
    } catch (e) {
      console.error('Profile delete error:', e);
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <Card
        title="Family Profiles"
        subtitle="Each person can be colour-coded and tagged on events."
        actions={
          <Button
            variant="secondary" size="sm"
            icon={<Icon name="plus" className="w-4 h-4" />}
            onClick={() => setModal({ mode: 'add' })}
          >
            Add
          </Button>
        }
        padding="md"
      >
        {loading ? (
          <div className="py-8 flex justify-center"><Spinner /></div>
        ) : profiles?.length === 0 ? (
          <p className="text-body-sm text-text-muted py-4">No profiles yet. Add a family member to get started.</p>
        ) : (
          <div>
            {profiles.map((p) => (
              <ProfileCard
                key={p.id}
                profile={p}
                onEdit={(pr) => setModal({ mode: 'edit', profile: pr })}
                onDelete={(pr) => setModal({ mode: 'delete', profile: pr })}
              />
            ))}
          </div>
        )}
      </Card>

      {/* Add / Edit modal */}
      <Modal
        open={modal?.mode === 'add' || modal?.mode === 'edit'}
        onClose={() => setModal(null)}
        title={modal?.mode === 'add' ? 'Add Profile' : 'Edit Profile'}
        footer={
          <>
            <Button variant="ghost" onClick={() => setModal(null)}>Cancel</Button>
            <Button
              variant="primary"
              loading={saving}
              onClick={() => document.querySelector('#profile-form')?.requestSubmit()}
            >
              Save
            </Button>
          </>
        }
      >
        <form
          id="profile-form"
          onSubmit={(e) => {
            e.preventDefault();
            const fd = new FormData(e.target);
            // We rely on ProfileForm's own submit handler instead
          }}
        >
          {(modal?.mode === 'add' || modal?.mode === 'edit') && (
            <ProfileForm
              initial={modal.profile}
              onSave={handleSave}
              onCancel={() => setModal(null)}
              saving={saving}
            />
          )}
        </form>
      </Modal>

      {/* Delete confirm */}
      <Modal
        open={modal?.mode === 'delete'}
        onClose={() => setModal(null)}
        title="Remove Profile"
        size="sm"
        footer={
          <>
            <Button variant="ghost" onClick={() => setModal(null)}>Cancel</Button>
            <Button variant="danger" loading={saving} onClick={handleDelete}>Remove</Button>
          </>
        }
      >
        <p className="text-body text-text-secondary pb-2">
          Remove <strong className="text-text-primary">{modal?.profile?.name}</strong>? Events tagged with this profile will be untagged.
        </p>
      </Modal>
    </>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// Section: Calendar
// ─────────────────────────────────────────────────────────────────────────────

const CalDAVForm = ({ onAdd, onCancel }) => {
  const [url,      setUrl]      = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [label,    setLabel]    = useState('');
  const [saving,   setSaving]   = useState(false);
  const [error,    setError]    = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!url.trim()) { setError('URL is required'); return; }
    setSaving(true);
    try {
      await onAdd({ url, username, password, label: label || undefined });
    } catch (err) {
      setError(err.detail ?? err.message ?? 'Connection failed');
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <TextInput label="CalDAV URL"    value={url}      onChange={(e) => setUrl(e.target.value)}      placeholder="https://caldav.example.com/calendar/" required error={error} />
      <TextInput label="Username"      value={username} onChange={(e) => setUsername(e.target.value)} placeholder="you@example.com" />
      <TextInput label="Password"      value={password} onChange={(e) => setPassword(e.target.value)} type="password" placeholder="App password" />
      <TextInput label="Display label" value={label}    onChange={(e) => setLabel(e.target.value)}    placeholder="Home calendar" />
      <div className="flex gap-3 pt-2">
        <Button variant="ghost"   onClick={onCancel} type="button">Cancel</Button>
        <Button variant="primary" loading={saving} type="submit">Connect</Button>
      </div>
    </form>
  );
};

const OAuthButton = ({ provider, label, icon, onConnect, onRevoke }) => {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    ApiClient.getOAuthStatus(provider)
      .then(setStatus)
      .catch(() => setStatus({ connected: false }))
      .finally(() => setLoading(false));
  }, [provider]);

  const handleConnect = async () => {
    try {
      const { url } = await ApiClient.getOAuthUrl(provider);
      window.location.href = url;
    } catch (e) {
      console.error('OAuth error:', e);
    }
  };

  const handleRevoke = async () => {
    setLoading(true);
    try {
      await ApiClient.revokeOAuth(provider);
      setStatus({ connected: false });
      onRevoke?.();
    } catch (e) {
      console.error('Revoke error:', e);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex items-center justify-between gap-3 py-3 border-b border-surface-4/40 last:border-0">
      <div className="flex items-center gap-3">
        <span className="text-2xl" aria-hidden="true">{icon}</span>
        <div>
          <p className="text-body font-medium text-text-primary">{label}</p>
          {!loading && status?.account && (
            <p className="text-body-sm text-text-secondary">{status.account}</p>
          )}
        </div>
      </div>
      <div className="flex items-center gap-2">
        {loading ? (
          <Spinner size="sm" />
        ) : status?.connected ? (
          <>
            <StatusDot status="ok" />
            <Button variant="ghost" size="sm" onClick={handleRevoke}>Disconnect</Button>
          </>
        ) : (
          <Button variant="secondary" size="sm" onClick={handleConnect}>Connect</Button>
        )}
      </div>
    </div>
  );
};

const CalendarSection = () => {
  const fetcher = useCallback(() => ApiClient.getCalendarSources(), []);
  const { data: sources = [], loading, refetch } = useApi(fetcher, []);
  const [showCalDAV, setShowCalDAV] = useState(false);

  const handleAddCalDAV = async (data) => {
    await ApiClient.addCalDAVSource(data);
    refetch();
    setShowCalDAV(false);
  };

  const handleToggleSource = async (id, enabled) => {
    await ApiClient.updateCalendarSource(id, { enabled });
    refetch();
  };

  const handleSync = async () => {
    await ApiClient.triggerSync();
  };

  return (
    <div className="space-y-4">
      <Card title="Connected accounts" padding="md">
        <OAuthButton provider="google"    label="Google Calendar"  icon="📅" onRevoke={refetch} />
        <OAuthButton provider="microsoft" label="Microsoft 365"    icon="📆" onRevoke={refetch} />

        <div className="pt-2">
          {!showCalDAV ? (
            <Button
              variant="ghost" size="sm"
              icon={<Icon name="plus" className="w-4 h-4" />}
              onClick={() => setShowCalDAV(true)}
            >
              Add CalDAV server
            </Button>
          ) : (
            <div className="pt-2">
              <CalDAVForm onAdd={handleAddCalDAV} onCancel={() => setShowCalDAV(false)} />
            </div>
          )}
        </div>
      </Card>

      <Card title="Calendar sources" padding="md"
        actions={
          <Button variant="ghost" size="sm" onClick={handleSync} icon={<Icon name="refresh" className="w-4 h-4" />}>Sync now</Button>
        }
      >
        {loading ? (
          <div className="py-6 flex justify-center"><Spinner /></div>
        ) : sources.length === 0 ? (
          <p className="text-body-sm text-text-muted py-3">No calendars connected yet.</p>
        ) : (
          sources.map((src) => (
            <div key={src.id} className="flex items-center gap-3 py-3 border-b border-surface-4/40 last:border-0">
              <StatusDot status={src.status} />
              <div className="flex-1 min-w-0">
                <p className="text-body font-medium text-text-primary truncate-1">{src.label}</p>
                <p className="text-body-sm text-text-muted capitalize">{src.kind}</p>
              </div>
              <Toggle
                checked={src.enabled}
                onChange={(v) => handleToggleSource(src.id, v)}
                size="sm"
              />
            </div>
          ))
        )}
      </Card>
    </div>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// Section: Photos
// ─────────────────────────────────────────────────────────────────────────────

const PhotosSection = () => {
  // Read/write canonical slideshow manifest keys:
  //   display_duration_ms — per-photo dwell time   (default 8000 ms)
  //   transition_speed_ms — crossfade duration      (default 1200 ms)
  const settingsFetcher = useCallback(() => ApiClient.getPluginSettings('slideshow'), []);
  const { data: pluginSettings, loading, refetch } = useApi(settingsFetcher, null);

  // Drafts are shown in seconds in the UI; stored as ms in the manifest
  const [draftDuration,   setDraftDuration]   = useState('');
  const [draftTransition, setDraftTransition] = useState('');

  useEffect(() => {
    if (!loading) {
      setDraftDuration(String(Math.round((pluginSettings?.display_duration_ms ?? 8_000) / 1000)));
      setDraftTransition(String(Math.round((pluginSettings?.transition_speed_ms ?? 1_200) / 1000)));
    }
  }, [loading, pluginSettings]);

  const handleSave = useCallback(async () => {
    const durSecs = parseInt(draftDuration, 10);
    const transSecs = parseFloat(draftTransition);
    if (isNaN(durSecs) || durSecs < 3) return;
    await ApiClient.setPluginSettings('slideshow', {
      ...(pluginSettings ?? {}),
      display_duration_ms: durSecs * 1000,
      transition_speed_ms: !isNaN(transSecs) ? Math.round(transSecs * 1000) : 1_200,
    });
    refetch();
  }, [draftDuration, draftTransition, pluginSettings, refetch]);

  return (
    <div className="space-y-4">
      <Card title="Google Photos" padding="md">
        <OAuthButton provider="google" label="Google Photos" icon="🖼️" />
      </Card>
      <Card title="Slideshow settings" padding="md">
        <div className="grid grid-cols-2 gap-3">
          <TextInput
            label="Photo duration (seconds)"
            type="number"
            value={draftDuration}
            onChange={(e) => setDraftDuration(e.target.value)}
            description="Minimum 3 s"
          />
          <TextInput
            label="Crossfade speed (seconds)"
            type="number"
            value={draftTransition}
            onChange={(e) => setDraftTransition(e.target.value)}
            description="e.g. 1.2"
          />
        </div>
        <Button
          variant="secondary"
          className="mt-4"
          onClick={handleSave}
        >
          Save
        </Button>
      </Card>
    </div>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// Section: Weather
// ─────────────────────────────────────────────────────────────────────────────

const WeatherSection = () => {
  const { value: pluginSettings, loading } = useApi(
    useCallback(() => ApiClient.getPluginSettings('weather'), []),
    null
  );
  const [form, setForm] = useState({ latitude: '', longitude: '', location_label: '', units: 'metric' });
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (pluginSettings) setForm({ ...form, ...pluginSettings });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pluginSettings]);

  const handleSave = async () => {
    setSaving(true);
    try {
      await ApiClient.setPluginSettings('weather', form);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (e) {
      console.error('Weather settings error:', e);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card title="Weather settings" subtitle="Powered by Open-Meteo — no API key required." padding="md">
      {loading ? (
        <div className="py-6 flex justify-center"><Spinner /></div>
      ) : (
        <div className="space-y-4">
          <TextInput
            label="Location name"
            value={form.location_label}
            onChange={(e) => setForm({ ...form, location_label: e.target.value })}
            placeholder="Melbourne"
          />
          <div className="grid grid-cols-2 gap-3">
            <TextInput
              label="Latitude"
              type="number"
              value={form.latitude}
              onChange={(e) => setForm({ ...form, latitude: e.target.value })}
              placeholder="-37.8136"
            />
            <TextInput
              label="Longitude"
              type="number"
              value={form.longitude}
              onChange={(e) => setForm({ ...form, longitude: e.target.value })}
              placeholder="144.9631"
            />
          </div>
          <div>
            <span className="text-body-sm font-medium text-text-secondary block mb-2">Units</span>
            <div className="flex gap-2">
              {['metric', 'imperial'].map((u) => (
                <button
                  key={u}
                  type="button"
                  onClick={() => setForm({ ...form, units: u })}
                  className={`px-4 py-2 rounded-lg text-body-sm font-medium transition-all duration-[150ms]
                    ${form.units === u
                      ? 'bg-accent-500 text-white'
                      : 'bg-surface-3 text-text-secondary hover:bg-surface-4'
                    }`}
                >
                  {u === 'metric' ? '°C (metric)' : '°F (imperial)'}
                </button>
              ))}
            </div>
          </div>
          <Button
            variant="primary"
            loading={saving}
            onClick={handleSave}
            icon={saved ? <Icon name="check" className="w-4 h-4" /> : undefined}
          >
            {saved ? 'Saved' : 'Save'}
          </Button>
        </div>
      )}
    </Card>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// Section: Screensaver
// ─────────────────────────────────────────────────────────────────────────────

const ScreensaverSection = () => {
  const { value: enabled, set: setEnabled, loading: loadingEnabled } =
    useSettings('display.screensaver_enabled', true);
  const { value: timeout, set: setTimeout_, loading } =
    useSettings('display.screensaver_timeout_s', 300);
  const [draft, setDraft] = useState('');

  useEffect(() => {
    if (!loading) setDraft(String(Math.round((timeout ?? 300) / 60)));
  }, [loading, timeout]);

  const handleSave = async () => {
    const mins = parseInt(draft, 10);
    if (!isNaN(mins) && mins >= 1) await setTimeout_(mins * 60);
  };

  const isOff = enabled === false;

  return (
    <Card title="Screensaver" subtitle="Starts after inactivity when the dashboard is displayed." padding="md">
      <Toggle
        checked={!isOff}
        onChange={(v) => setEnabled(v)}
        disabled={loadingEnabled}
        label="Enable screensaver"
        description="Show the full-screen photo slideshow after a period of inactivity."
      />

      <div
        className={`flex items-center gap-3 mt-5 transition-opacity duration-200 ${
          isOff ? 'opacity-40 pointer-events-none' : ''
        }`}
        aria-hidden={isOff}
      >
        <TextInput
          label="Idle timeout (minutes)"
          type="number"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          description="Minimum 1 minute"
          className="flex-1"
          disabled={isOff}
        />
        <Button
          variant="secondary"
          className="mt-6 flex-shrink-0"
          onClick={handleSave}
          disabled={isOff}
        >
          Save
        </Button>
      </div>
    </Card>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// Section: Plugins
// ─────────────────────────────────────────────────────────────────────────────

const PluginsSection = () => {
  const fetcher = useCallback(() => ApiClient.getPlugins(), []);
  const { data: plugins = [], loading, refetch } = useApi(fetcher, []);

  const handleToggle = async (name, enabled) => {
    await ApiClient.setPluginEnabled(name, enabled);
    refetch();
  };

  return (
    <Card title="Plugins" subtitle="Enable or disable dashboard plugins." padding="md">
      {loading ? (
        <div className="py-6 flex justify-center"><Spinner /></div>
      ) : plugins.length === 0 ? (
        <p className="text-body-sm text-text-muted py-3">No plugins installed.</p>
      ) : (
        plugins.map((plugin) => (
          <div key={plugin.name} className="py-3 border-b border-surface-4/40 last:border-0">
            <Toggle
              checked={plugin.enabled}
              onChange={(v) => handleToggle(plugin.name, v)}
              label={plugin.name}
              description={plugin.description}
            />
            <div className="flex gap-2 mt-1.5 ml-0">
              {plugin.has_background_tasks && (
                <span className="text-caption text-text-muted bg-surface-3 px-2 py-0.5 rounded-pill">background tasks</span>
              )}
              {plugin.has_router && (
                <span className="text-caption text-text-muted bg-surface-3 px-2 py-0.5 rounded-pill">router</span>
              )}
              {plugin.frontend_component && (
                <span className="text-caption text-accent-400 bg-accent-500/10 px-2 py-0.5 rounded-pill">{plugin.frontend_component}</span>
              )}
            </div>
          </div>
        ))
      )}
    </Card>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// Section map + sidebar navigation
// ─────────────────────────────────────────────────────────────────────────────

const SECTIONS = [
  { id: 'profiles',    label: 'Profiles',   icon: 'users',    component: ProfilesSection   },
  { id: 'calendar',    label: 'Calendar',   icon: 'calendar', component: CalendarSection   },
  { id: 'photos',      label: 'Photos',     icon: 'image',    component: PhotosSection     },
  { id: 'weather',     label: 'Weather',    icon: 'cloud',    component: WeatherSection    },
  { id: 'screensaver', label: 'Screensaver',icon: 'clock',    component: ScreensaverSection },
  { id: 'plugins',     label: 'Plugins',    icon: 'plugin',   component: PluginsSection    },
];

// ─────────────────────────────────────────────────────────────────────────────
// Main Settings component
// ─────────────────────────────────────────────────────────────────────────────

const Settings = ({ onBack }) => {
  const [activeSection, setActiveSection] = useState('profiles');

  const current = SECTIONS.find((s) => s.id === activeSection) ?? SECTIONS[0];
  const SectionComponent = current.component;

  // Check if OAuth callback redirected us here
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const oauthProvider = params.get('oauth');
    if (oauthProvider) {
      setActiveSection('calendar');
      // Clear the query param without a full reload
      const url = new URL(window.location.href);
      url.searchParams.delete('oauth');
      window.history.replaceState({}, '', url.toString());
    }
  }, []);

  return (
    <div className="min-h-dvh bg-surface-0 flex flex-col">
      {/* ── Header ────────────────────────────────────────────────────────── */}
      <header className="flex items-center gap-3 px-5 py-4 border-b border-surface-4 flex-shrink-0">
        <Button
          variant="ghost"
          size="md"
          onClick={onBack}
          icon={<Icon name="arrow-left" className="w-5 h-5" />}
          aria-label="Back to home"
        >
          Back
        </Button>
        <h1 className="text-title-lg font-semibold text-text-primary ml-1">Settings</h1>
      </header>

      {/* ── Body ──────────────────────────────────────────────────────────── */}
      <div className="flex flex-1 min-h-0">
        {/* ── Sidebar — hidden on small screens ─────────────────────────── */}
        <nav
          className="hidden sm:flex flex-col w-56 flex-shrink-0 border-r border-surface-4 py-3 overflow-y-auto"
          aria-label="Settings sections"
        >
          {SECTIONS.map((s) => {
            const active = s.id === activeSection;
            return (
              <button
                key={s.id}
                type="button"
                onClick={() => setActiveSection(s.id)}
                className={[
                  'flex items-center gap-3 px-4 py-3 text-left rounded-lg mx-2 transition-all duration-[150ms]',
                  active
                    ? 'bg-accent-500/10 text-accent-400'
                    : 'text-text-secondary hover:bg-surface-3 hover:text-text-primary',
                ].join(' ')}
                aria-current={active ? 'page' : undefined}
              >
                <Icon name={s.icon} className="w-5 h-5 flex-shrink-0" />
                <span className="text-body font-medium">{s.label}</span>
              </button>
            );
          })}
        </nav>

        {/* ── Tab bar — shown on small screens ──────────────────────────── */}
        <div
          className="sm:hidden flex overflow-x-auto border-b border-surface-4 px-2 py-1 gap-1 flex-shrink-0"
          role="tablist"
          aria-label="Settings sections"
        >
          {SECTIONS.map((s) => {
            const active = s.id === activeSection;
            return (
              <button
                key={s.id}
                type="button"
                role="tab"
                aria-selected={active}
                onClick={() => setActiveSection(s.id)}
                className={[
                  'flex-shrink-0 flex items-center gap-1.5 px-3 py-2 rounded-lg text-body-sm font-medium transition-all duration-[150ms]',
                  active
                    ? 'bg-accent-500/10 text-accent-400'
                    : 'text-text-secondary hover:bg-surface-3',
                ].join(' ')}
              >
                <Icon name={s.icon} className="w-4 h-4" />
                {s.label}
              </button>
            );
          })}
        </div>

        {/* ── Content panel ─────────────────────────────────────────────── */}
        <main
          className="flex-1 min-w-0 overflow-y-auto p-5 sm:p-7 space-y-5"
          role="tabpanel"
          aria-label={current.label}
        >
          <SectionComponent key={activeSection} />
        </main>
      </div>
    </div>
  );
};

export default Settings;
