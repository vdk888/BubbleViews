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
      <div className="page-shell">
        <div className="card p-4 bg-[var(--card)]">
          <p className="muted">Selectionnez une persona pour acceder aux parametres.</p>
        </div>
      </div>
    );
  }

  const autoPostingEnabled = settings?.config.auto_posting_enabled as boolean | undefined;

  return (
    <div className="page-shell">
      <div className="mb-6">
        <h1>Settings</h1>
        <p className="muted max-w-2xl">
          Ajustez le comportement de l'agent en coherence avec la promesse Bubble : transparence et controle.
        </p>
      </div>

      {error && (
        <div className="border border-red-200 bg-red-50 rounded-lg p-4 mb-6">
          <p className="text-red-800">{error}</p>
        </div>
      )}

      {loading && (
        <div className="space-y-6">
          {[1, 2, 3].map((i) => (
            <div key={i} className="card p-6 animate-pulse">
              <div className="h-4 bg-[var(--card)] rounded w-1/3 mb-2"></div>
              <div className="h-4 bg-[var(--card)] rounded w-2/3"></div>
            </div>
          ))}
        </div>
      )}

      {!loading && settings && (
        <div className="space-y-6">
          <div className="card border-[var(--border)]">
            <div className="px-6 py-4 border-b border-[var(--border)]">
              <h2 className="text-lg font-semibold">Agent Behavior</h2>
            </div>
            <div className="p-6 space-y-4">
              <div className="flex items-center justify-between py-3">
                <div className="flex-1">
                  <h3 className="text-sm font-semibold text-[var(--primary)] mb-1">Auto-Posting</h3>
                  <p className="text-sm muted">
                    Autoriser l'agent a publier en autonomie sans relecture manuelle.
                  </p>
                </div>
                <button
                  onClick={() => handleToggleSetting("auto_posting_enabled", autoPostingEnabled || false)}
                  disabled={saving}
                  className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-[var(--primary)] focus:ring-offset-2 disabled:opacity-50 ${
                    autoPostingEnabled ? "bg-[var(--primary)]" : "bg-[var(--border)]"
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

          <div className="card border-[var(--border)]">
            <div className="px-6 py-4 border-b border-[var(--border)]">
              <h2 className="text-lg font-semibold">Persona Information</h2>
            </div>
            <div className="p-6">
              <dl className="space-y-4">
                <div>
                  <dt className="text-sm font-semibold text-[var(--text-secondary)]">Persona ID</dt>
                  <dd className="mt-1 text-sm font-mono text-[var(--primary)] break-all">
                    {selectedPersonaId}
                  </dd>
                </div>
              </dl>
            </div>
          </div>

          <div className="card border-[var(--border)]">
            <div className="px-6 py-4 border-b border-[var(--border)]">
              <h2 className="text-lg font-semibold">Raw Configuration</h2>
            </div>
            <div className="p-6">
              <pre className="text-xs bg-[var(--card)] p-4 rounded border border-[var(--border)] overflow-x-auto">
                {JSON.stringify(settings.config, null, 2)}
              </pre>
            </div>
          </div>

          <div className="border border-[var(--chart-border)] bg-[var(--chart-bg-light)] rounded-lg p-4">
            <div className="flex items-start">
              <div className="flex-shrink-0 h-9 w-9 rounded-full border border-[var(--chart-border)] flex items-center justify-center">
                <span className="text-[var(--chart-primary)] font-bold">i</span>
              </div>
              <div className="ml-3">
                <h3 className="text-sm font-semibold text-[var(--primary)]">Stockage des parametres</h3>
                <p className="text-sm text-[var(--text-secondary)] mt-1">
                  Chaque persona possede ses propres preferences stockees en base. Les changements sont immediats pour
                  l'agent.
                </p>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
