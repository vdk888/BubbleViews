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
      // Remove from list
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
      // Remove from list
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
      // Reload settings
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
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg p-4">
          <p className="text-yellow-800 dark:text-yellow-200">
            Please select a persona to view moderation queue
          </p>
        </div>
      </div>
    );
  }

  const autoPostingEnabled = settings?.config.auto_posting_enabled as boolean | undefined;

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="mb-6">
        <h1 className="text-3xl font-bold text-zinc-900 dark:text-white mb-2">
          Moderation Queue
        </h1>
        <p className="text-zinc-600 dark:text-zinc-400">
          Review and approve pending posts before they go live
        </p>
      </div>

      {/* Auto-posting toggle */}
      <div className="mb-6 bg-white dark:bg-zinc-800 rounded-lg shadow p-6 border border-zinc-200 dark:border-zinc-700">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-zinc-900 dark:text-white mb-1">
              Auto-Posting Mode
            </h2>
            <p className="text-sm text-zinc-600 dark:text-zinc-400">
              {autoPostingEnabled
                ? "Agent posts autonomously without review"
                : "All posts require manual approval"}
            </p>
          </div>
          <button
            onClick={handleToggleAutoPosting}
            disabled={loading}
            className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 ${
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

      {/* Error State */}
      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4 mb-6">
          <p className="text-red-800 dark:text-red-200">{error}</p>
        </div>
      )}

      {/* Loading State */}
      {loading && (
        <div className="space-y-4">
          {[1, 2].map((i) => (
            <div
              key={i}
              className="bg-white dark:bg-zinc-800 rounded-lg shadow p-6 border border-zinc-200 dark:border-zinc-700 animate-pulse"
            >
              <div className="h-4 bg-zinc-200 dark:bg-zinc-700 rounded w-1/4 mb-2"></div>
              <div className="h-4 bg-zinc-200 dark:bg-zinc-700 rounded w-3/4 mb-4"></div>
              <div className="h-8 bg-zinc-200 dark:bg-zinc-700 rounded w-1/3"></div>
            </div>
          ))}
        </div>
      )}

      {/* Empty State */}
      {!loading && pendingPosts.length === 0 && (
        <div className="bg-white dark:bg-zinc-800 rounded-lg shadow p-8 border border-zinc-200 dark:border-zinc-700 text-center">
          <div className="text-4xl mb-4">✅</div>
          <p className="text-zinc-900 dark:text-white font-medium mb-2">
            Queue is empty
          </p>
          <p className="text-zinc-500 dark:text-zinc-400">
            No posts awaiting review at this time
          </p>
        </div>
      )}

      {/* Pending Posts List */}
      {!loading && pendingPosts.length > 0 && (
        <div className="space-y-4">
          {pendingPosts.map((item) => (
            <div
              key={item.id}
              className="bg-white dark:bg-zinc-800 rounded-lg shadow p-6 border border-zinc-200 dark:border-zinc-700"
            >
              <div className="flex items-start justify-between mb-3">
                <div className="flex items-center gap-2">
                  <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300">
                    {item.post_type || "comment"}
                  </span>
                  {item.target_subreddit && (
                    <span className="text-sm text-zinc-600 dark:text-zinc-400">
                      r/{item.target_subreddit}
                    </span>
                  )}
                </div>
                <span className="text-sm text-zinc-500 dark:text-zinc-500">
                  {formatDate(item.created_at)}
                </span>
              </div>

              <div className="mb-4 p-4 bg-zinc-50 dark:bg-zinc-900 rounded border border-zinc-200 dark:border-zinc-700">
                <p className="text-zinc-900 dark:text-white whitespace-pre-wrap">
                  {truncate(item.content, 500)}
                </p>
              </div>

              <div className="flex items-center gap-3">
                <button
                  onClick={() => handleApprove(item)}
                  disabled={actionInProgress === item.id}
                  className="px-4 py-2 bg-green-600 text-white rounded-md hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed text-sm font-medium"
                >
                  {actionInProgress === item.id ? "Processing..." : "Approve & Post"}
                </button>
                <button
                  onClick={() => handleReject(item)}
                  disabled={actionInProgress === item.id}
                  className="px-4 py-2 bg-red-600 text-white rounded-md hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed text-sm font-medium"
                >
                  Reject
                </button>
                <button
                  onClick={() => {
                    const fullContent = JSON.stringify(item, null, 2);
                    alert(fullContent);
                  }}
                  className="px-4 py-2 bg-zinc-200 dark:bg-zinc-700 text-zinc-900 dark:text-white rounded-md hover:bg-zinc-300 dark:hover:bg-zinc-600 text-sm font-medium"
                >
                  View Details
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
