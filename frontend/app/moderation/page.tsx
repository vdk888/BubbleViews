"use client";

import { useEffect, useState } from "react";
import { usePersona } from "@/hooks/usePersona";
import { apiClient, PendingItem, SettingsResponse } from "@/lib/api-client";

export default function ModerationPage() {
  const { selectedPersonaId } = usePersona();
  const [pendingPosts, setPendingPosts] = useState<PendingItem[]>([]);
  const [settings, setSettings] = useState<SettingsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionInProgress, setActionInProgress] = useState<string | null>(null);

  useEffect(() => {
    if (selectedPersonaId) {
      loadData();
    }
  }, [selectedPersonaId]);

  const loadData = async () => {
    if (!selectedPersonaId) return;

    try {
      setLoading(true);
      const [posts, config] = await Promise.all([
        apiClient.getPendingPosts(selectedPersonaId),
        apiClient.getSettings(selectedPersonaId),
      ]);
      setPendingPosts(posts);
      setSettings(config);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load data");
    } finally {
      setLoading(false);
    }
  };

  const handleApprove = async (item: PendingItem) => {
    if (!selectedPersonaId || actionInProgress) return;

    try {
      setActionInProgress(item.id);
      await apiClient.approvePost({
        item_id: item.id,
        persona_id: selectedPersonaId,
      });
      setPendingPosts((prev) => prev.filter((p) => p.id !== item.id));
    } catch (err) {
      alert(`Failed to approve: ${err instanceof Error ? err.message : "Unknown error"}`);
    } finally {
      setActionInProgress(null);
    }
  };

  const handleReject = async (item: PendingItem) => {
    if (!selectedPersonaId || actionInProgress) return;

    try {
      setActionInProgress(item.id);
      await apiClient.rejectPost({
        item_id: item.id,
        persona_id: selectedPersonaId,
      });
      setPendingPosts((prev) => prev.filter((p) => p.id !== item.id));
    } catch (err) {
      alert(`Failed to reject: ${err instanceof Error ? err.message : "Unknown error"}`);
    } finally {
      setActionInProgress(null);
    }
  };

  const handleToggleAutoPosting = async () => {
    if (!selectedPersonaId || !settings) return;

    const currentValue = settings.config.auto_posting_enabled as boolean;
    const confirmMessage = currentValue
      ? "Disable auto-posting? The agent will queue all posts for review."
      : "Enable auto-posting? The agent will post autonomously without review.";

    if (!confirm(confirmMessage)) return;

    try {
      await apiClient.updateSetting({
        persona_id: selectedPersonaId,
        key: "auto_posting_enabled",
        value: !currentValue,
      });
      const newSettings = await apiClient.getSettings(selectedPersonaId);
      setSettings(newSettings);
    } catch (err) {
      alert(`Failed to update setting: ${err instanceof Error ? err.message : "Unknown error"}`);
    }
  };

  const formatDate = (dateString: string | null) => {
    if (!dateString) return "Unknown";
    const date = new Date(dateString);
    return new Intl.DateTimeFormat("en-US", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }).format(date);
  };

  const truncate = (text: string, maxLength: number) => {
    if (text.length <= maxLength) return text;
    return text.substring(0, maxLength) + "...";
  };

  if (!selectedPersonaId) {
    return (
      <div className="page-shell">
        <div className="card p-4 bg-[var(--card)]">
          <p className="muted">Selectionnez une persona pour acceder a la moderation.</p>
        </div>
      </div>
    );
  }

  const autoPostingEnabled = settings?.config.auto_posting_enabled as boolean | undefined;

  return (
    <div className="page-shell">
      <div className="mb-6">
        <h1>Moderation Queue</h1>
        <p className="muted max-w-2xl">
          Gouvernez chaque publication avant diffusion, en coherence avec la transparence Bubble.
        </p>
      </div>

      <div className="card p-6 mb-6">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold">Auto-Posting Mode</h2>
            <p className="text-sm muted">
              {autoPostingEnabled
                ? "L'agent publie en autonomie."
                : "Toutes les publications necessitent une validation."}
            </p>
          </div>
          <button
            onClick={handleToggleAutoPosting}
            disabled={loading}
            className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-[var(--primary)] focus:ring-offset-2 ${
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

      {error && (
        <div className="border border-red-200 bg-red-50 rounded-lg p-4 mb-6">
          <p className="text-red-800">{error}</p>
        </div>
      )}

      {loading && (
        <div className="space-y-4">
          {[1, 2].map((i) => (
            <div key={i} className="card p-6 animate-pulse">
              <div className="h-4 bg-[var(--card)] rounded w-1/4 mb-2"></div>
              <div className="h-4 bg-[var(--card)] rounded w-3/4 mb-4"></div>
              <div className="h-8 bg-[var(--card)] rounded w-1/3"></div>
            </div>
          ))}
        </div>
      )}

      {!loading && pendingPosts.length === 0 && (
        <div className="card p-8 text-center">
          <p className="text-xl font-bold mb-2 text-[var(--primary)]">Queue vide</p>
          <p className="muted">Aucun contenu en attente pour le moment.</p>
        </div>
      )}

      {!loading && pendingPosts.length > 0 && (
        <div className="space-y-4">
          {pendingPosts.map((item) => (
            <div key={item.id} className="card p-6">
              <div className="flex items-start justify-between mb-3">
                <div className="flex items-center gap-2">
                  <span className="chip text-xs">{item.post_type || "comment"}</span>
                  {item.target_subreddit && (
                    <span className="text-sm text-[var(--text-secondary)]">
                      r/{item.target_subreddit}
                    </span>
                  )}
                </div>
                <span className="text-sm text-[var(--text-secondary)]">{formatDate(item.created_at)}</span>
              </div>

              <div className="mb-4 p-4 bg-[var(--card)] rounded border border-[var(--border)]">
                <p className="text-[var(--primary)] whitespace-pre-wrap">{truncate(item.content, 500)}</p>
              </div>

              <div className="flex items-center gap-3">
                <button
                  onClick={() => handleApprove(item)}
                  disabled={actionInProgress === item.id}
                  className="pill-button text-sm disabled:opacity-60 disabled:cursor-not-allowed"
                >
                  {actionInProgress === item.id ? "Traitement..." : "Approuver & poster"}
                </button>
                <button
                  onClick={() => handleReject(item)}
                  disabled={actionInProgress === item.id}
                  className="soft-button text-sm disabled:opacity-60 disabled:cursor-not-allowed"
                >
                  Rejeter
                </button>
                <button
                  onClick={() => alert(JSON.stringify(item, null, 2))}
                  className="soft-button text-sm"
                >
                  Details
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
