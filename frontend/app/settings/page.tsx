"use client";

import { useEffect, useState } from "react";
import { usePersona } from "@/hooks/usePersona";
import { apiClient, SettingsResponse } from "@/lib/api-client";

export default function SettingsPage() {
  const { selectedPersonaId } = usePersona();
  const [settings, setSettings] = useState<SettingsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (selectedPersonaId) {
      loadSettings();
    }
  }, [selectedPersonaId]);

  const loadSettings = async () => {
    if (!selectedPersonaId) return;

    try {
      setLoading(true);
      const data = await apiClient.getSettings(selectedPersonaId);
      setSettings(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load settings");
    } finally {
      setLoading(false);
    }
  };

  const handleToggleSetting = async (key: string, currentValue: boolean) => {
    if (!selectedPersonaId || saving) return;

    try {
      setSaving(true);
      await apiClient.updateSetting({
        persona_id: selectedPersonaId,
        key,
        value: !currentValue,
      });
      await loadSettings();
    } catch (err) {
      alert(`Failed to update setting: ${err instanceof Error ? err.message : "Unknown error"}`);
    } finally {
      setSaving(false);
    }
  };

  if (!selectedPersonaId) {
    return (
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg p-4">
          <p className="text-yellow-800 dark:text-yellow-200">
            Please select a persona to view settings
          </p>
        </div>
      </div>
    );
  }

  const autoPostingEnabled = settings?.config.auto_posting_enabled as boolean | undefined;

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="mb-6">
        <h1 className="text-3xl font-bold text-zinc-900 dark:text-white mb-2">
          Settings
        </h1>
        <p className="text-zinc-600 dark:text-zinc-400">
          Configure agent behavior and preferences
        </p>
      </div>

      {/* Error State */}
      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4 mb-6">
          <p className="text-red-800 dark:text-red-200">{error}</p>
        </div>
      )}

      {/* Loading State */}
      {loading && (
        <div className="space-y-6">
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              className="bg-white dark:bg-zinc-800 rounded-lg shadow p-6 border border-zinc-200 dark:border-zinc-700 animate-pulse"
            >
              <div className="h-4 bg-zinc-200 dark:bg-zinc-700 rounded w-1/3 mb-2"></div>
              <div className="h-4 bg-zinc-200 dark:bg-zinc-700 rounded w-2/3"></div>
            </div>
          ))}
        </div>
      )}

      {/* Settings List */}
      {!loading && settings && (
        <div className="space-y-6">
          {/* Agent Behavior */}
          <div className="bg-white dark:bg-zinc-800 rounded-lg shadow border border-zinc-200 dark:border-zinc-700">
            <div className="px-6 py-4 border-b border-zinc-200 dark:border-zinc-700">
              <h2 className="text-lg font-semibold text-zinc-900 dark:text-white">
                Agent Behavior
              </h2>
            </div>
            <div className="p-6 space-y-4">
              <div className="flex items-center justify-between py-3">
                <div className="flex-1">
                  <h3 className="text-sm font-medium text-zinc-900 dark:text-white mb-1">
                    Auto-Posting
                  </h3>
                  <p className="text-sm text-zinc-600 dark:text-zinc-400">
                    Allow agent to post autonomously without manual review
                  </p>
                </div>
                <button
                  onClick={() => handleToggleSetting("auto_posting_enabled", autoPostingEnabled || false)}
                  disabled={saving}
                  className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50 ${
                    autoPostingEnabled
                      ? "bg-blue-600"
                      : "bg-zinc-200 dark:bg-zinc-700"
                  }`}
                >
                  <span
                    className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                      autoPostingEnabled ? "translate-x-6" : "translate-x-1"
                    }`}
                  />
                </button>
              </div>
            </div>
          </div>

          {/* Persona Information */}
          <div className="bg-white dark:bg-zinc-800 rounded-lg shadow border border-zinc-200 dark:border-zinc-700">
            <div className="px-6 py-4 border-b border-zinc-200 dark:border-zinc-700">
              <h2 className="text-lg font-semibold text-zinc-900 dark:text-white">
                Persona Information
              </h2>
            </div>
            <div className="p-6">
              <dl className="space-y-4">
                <div>
                  <dt className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
                    Persona ID
                  </dt>
                  <dd className="mt-1 text-sm text-zinc-900 dark:text-white font-mono">
                    {selectedPersonaId}
                  </dd>
                </div>
              </dl>
            </div>
          </div>

          {/* Raw Configuration */}
          <div className="bg-white dark:bg-zinc-800 rounded-lg shadow border border-zinc-200 dark:border-zinc-700">
            <div className="px-6 py-4 border-b border-zinc-200 dark:border-zinc-700">
              <h2 className="text-lg font-semibold text-zinc-900 dark:text-white">
                Raw Configuration
              </h2>
            </div>
            <div className="p-6">
              <pre className="text-xs bg-zinc-50 dark:bg-zinc-900 p-4 rounded border border-zinc-200 dark:border-zinc-700 overflow-x-auto">
                {JSON.stringify(settings.config, null, 2)}
              </pre>
            </div>
          </div>

          {/* Info */}
          <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
            <div className="flex items-start">
              <div className="flex-shrink-0">
                <span className="text-2xl">ℹ️</span>
              </div>
              <div className="ml-3">
                <h3 className="text-sm font-medium text-blue-800 dark:text-blue-200">
                  Settings Storage
                </h3>
                <div className="mt-2 text-sm text-blue-700 dark:text-blue-300">
                  <p>
                    Settings are stored per-persona in the database. Changes take effect immediately.
                    Use the auto-posting toggle to control whether the agent posts autonomously or
                    requires manual approval.
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
