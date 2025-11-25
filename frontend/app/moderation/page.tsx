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

              {/* Original Post Section */}
              {item.draft_metadata?.original_post && (
                <div className="mb-4 p-4 bg-blue-50 rounded border border-blue-200">
                  <div className="flex items-center justify-between mb-2">
                    <h4 className="font-semibold text-sm text-blue-800 flex items-center gap-2">
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
                      </svg>
                      Original Post
                    </h4>
                    {item.draft_metadata.original_post.reddit_id && (
                      <a
                        href={`https://reddit.com/r/${item.target_subreddit}/comments/${item.draft_metadata.original_post.reddit_id}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-xs text-blue-600 hover:text-blue-800 hover:underline flex items-center gap-1"
                      >
                        View on Reddit
                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                        </svg>
                      </a>
                    )}
                  </div>
                  {item.draft_metadata.original_post.author && (
                    <p className="text-xs text-blue-600 mb-1">
                      by u/{item.draft_metadata.original_post.author}
                    </p>
                  )}
                  {item.draft_metadata.original_post.title && (
                    <p className="font-medium text-blue-900 mb-2">
                      {item.draft_metadata.original_post.title}
                    </p>
                  )}
                  {item.draft_metadata.original_post.body && (
                    <p className="text-sm text-blue-800 whitespace-pre-wrap">
                      {truncate(item.draft_metadata.original_post.body, 500)}
                    </p>
                  )}
                </div>
              )}

              {/* Proposed Response */}
              <div className="mb-4">
                <h4 className="font-semibold text-sm text-[var(--text-secondary)] mb-2 flex items-center gap-2">
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6" />
                  </svg>
                  Proposed Response
                </h4>
                <div className="p-4 bg-[var(--card)] rounded border border-[var(--border)]">
                  <p className="text-[var(--primary)] whitespace-pre-wrap">{truncate(item.content, 500)}</p>
                </div>
              </div>

              {/* Belief Proposals Section */}
              {item.belief_proposals && (
                (item.belief_proposals.updates.length > 0 || item.belief_proposals.new_belief) && (
                  <div className="mb-4 p-4 bg-purple-50 rounded border border-purple-200">
                    <h4 className="font-semibold text-sm text-purple-800 mb-3 flex items-center gap-2">
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                      </svg>
                      Belief Changes (on approval)
                    </h4>

                    {/* Confidence Updates */}
                    {item.belief_proposals.updates.length > 0 && (
                      <div className="space-y-2 mb-3">
                        {item.belief_proposals.updates.map((update) => (
                          <div
                            key={update.belief_id}
                            className="flex items-center gap-3 text-sm bg-white p-2 rounded"
                          >
                            <span className="font-medium text-purple-900 flex-1 truncate">
                              {update.belief_title}
                            </span>
                            <div className="flex items-center gap-2">
                              <span className="text-gray-500">
                                {(update.current_confidence * 100).toFixed(0)}%
                              </span>
                              <span className="text-gray-400">→</span>
                              <span
                                className={
                                  update.proposed_confidence > update.current_confidence
                                    ? "text-green-600 font-semibold"
                                    : "text-red-600 font-semibold"
                                }
                              >
                                {(update.proposed_confidence * 100).toFixed(0)}%
                              </span>
                              <span
                                className={`text-xs px-1.5 py-0.5 rounded ${
                                  update.evidence_strength === "strong"
                                    ? "bg-green-100 text-green-700"
                                    : update.evidence_strength === "moderate"
                                    ? "bg-yellow-100 text-yellow-700"
                                    : "bg-gray-100 text-gray-600"
                                }`}
                              >
                                {update.evidence_strength}
                              </span>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}

                    {/* New Belief */}
                    {item.belief_proposals.new_belief && (
                      <div className="bg-green-50 border border-green-200 rounded p-3">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-xs font-semibold text-green-700 bg-green-100 px-2 py-0.5 rounded">
                            + New Belief
                          </span>
                          <span className="text-xs text-green-600">
                            {(item.belief_proposals.new_belief.initial_confidence * 100).toFixed(0)}% confidence
                          </span>
                        </div>
                        <p className="font-medium text-green-900">
                          {item.belief_proposals.new_belief.title}
                        </p>
                        <p className="text-sm text-green-700 mt-1">
                          {truncate(item.belief_proposals.new_belief.summary, 150)}
                        </p>
                        {item.belief_proposals.new_belief.tags.length > 0 && (
                          <div className="flex gap-1 mt-2">
                            {item.belief_proposals.new_belief.tags.map((tag) => (
                              <span
                                key={tag}
                                className="text-xs bg-green-100 text-green-700 px-1.5 py-0.5 rounded"
                              >
                                {tag}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )
              )}

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
