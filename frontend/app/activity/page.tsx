"use client";

import { useEffect, useState } from "react";
import { usePersona } from "@/hooks/usePersona";
import { apiClient, ActivityItem } from "@/lib/api-client";

export default function ActivityPage() {
  const { selectedPersonaId } = usePersona();
  const [activities, setActivities] = useState<ActivityItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [limit, setLimit] = useState(20);

  useEffect(() => {
    if (selectedPersonaId) {
      loadActivity();
    }
  }, [selectedPersonaId, limit]);

  const loadActivity = async () => {
    if (!selectedPersonaId) return;

    try {
      setLoading(true);
      const data = await apiClient.getActivity(selectedPersonaId, { limit });
      setActivities(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load activity");
    } finally {
      setLoading(false);
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

  const getRedditUrl = (item: ActivityItem) => {
    if (item.interaction_type === "comment") {
      return `https://reddit.com/r/${item.subreddit}/comments/${item.parent_id?.split("_")[1]}/_/${item.reddit_id}`;
    }
    return `https://reddit.com/r/${item.subreddit}/comments/${item.reddit_id}`;
  };

  if (!selectedPersonaId) {
    return (
      <div className="page-shell">
        <div className="card p-4 bg-[var(--card)]">
          <p className="muted">Selectionnez une persona pour consulter l'activite.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="page-shell">
      <div className="mb-6">
        <h1>Activity Feed</h1>
        <p className="muted max-w-2xl">
          Flux en direct des interactions Reddit realisees par l'agent Bubble.
        </p>
      </div>

      <div className="mb-6 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div className="flex items-center gap-3">
          <label className="text-sm text-[var(--text-secondary)]">Afficher</label>
          <select
            value={limit}
            onChange={(e) => setLimit(Number(e.target.value))}
            className="px-3 py-2 border border-[var(--border)] rounded-md text-sm bg-white shadow-sm"
          >
            {[10, 20, 50, 100].map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
          <span className="text-sm text-[var(--text-secondary)]">interactions</span>
        </div>
        <button
          onClick={loadActivity}
          disabled={loading}
          className="pill-button text-sm disabled:opacity-60 disabled:cursor-not-allowed"
        >
          {loading ? "Chargement..." : "Rafraichir"}
        </button>
      </div>

      {error && (
        <div className="border border-red-200 bg-red-50 rounded-lg p-4 mb-6">
          <p className="text-red-800">{error}</p>
        </div>
      )}

      {loading && (
        <div className="space-y-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="card p-6 animate-pulse">
              <div className="h-4 bg-[var(--card)] rounded w-1/4 mb-2"></div>
              <div className="h-4 bg-[var(--card)] rounded w-3/4 mb-2"></div>
              <div className="h-4 bg-[var(--card)] rounded w-1/2"></div>
            </div>
          ))}
        </div>
      )}

      {!loading && activities.length === 0 && (
        <div className="card p-8 text-center">
          <p className="muted">Aucune interaction encore. L agent n a pas encore publie.</p>
        </div>
      )}

      {!loading && activities.length > 0 && (
        <div className="space-y-4">
          {activities.map((item) => (
            <div key={item.id} className="card p-6">
              <div className="flex items-start justify-between mb-2">
                <div className="flex items-center gap-2">
                  <span className="chip text-xs capitalize">{item.interaction_type}</span>
                  <span className="text-sm text-[var(--text-secondary)]">r/{item.subreddit}</span>
                </div>
                <span className="text-sm text-[var(--text-secondary)]">{formatDate(item.created_at)}</span>
              </div>

              <p className="text-[var(--primary)] mb-3">{truncate(item.content, 300)}</p>

              <div className="flex items-center gap-4">
                <a
                  href={getRedditUrl(item)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm font-semibold hover:underline"
                >
                  Voir sur Reddit {" ->"}
                </a>
                {item.metadata.karma !== undefined && (
                  <span className="text-sm text-[var(--text-secondary)]">
                    {String(item.metadata.karma)} karma
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {!loading && activities.length > 0 && (
        <div className="mt-6 text-center text-sm muted">
          Affichage des {activities.length} interactions les plus recentes.
        </div>
      )}
    </div>
  );
}
