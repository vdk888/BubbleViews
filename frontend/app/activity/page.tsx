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
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg p-4">
          <p className="text-yellow-800 dark:text-yellow-200">
            Please select a persona to view activity
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="mb-6">
        <h1 className="text-3xl font-bold text-zinc-900 dark:text-white mb-2">
          Activity Feed
        </h1>
        <p className="text-zinc-600 dark:text-zinc-400">
          Recent Reddit interactions by the agent
        </p>
      </div>

      {/* Controls */}
      <div className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <label className="text-sm text-zinc-600 dark:text-zinc-400">
            Show:
          </label>
          <select
            value={limit}
            onChange={(e) => setLimit(Number(e.target.value))}
            className="px-3 py-2 border border-zinc-300 dark:border-zinc-600 rounded-md text-sm bg-white dark:bg-zinc-800 text-zinc-900 dark:text-white"
          >
            <option value={10}>10</option>
            <option value={20}>20</option>
            <option value={50}>50</option>
            <option value={100}>100</option>
          </select>
          <span className="text-sm text-zinc-600 dark:text-zinc-400">
            interactions
          </span>
        </div>
        <button
          onClick={loadActivity}
          disabled={loading}
          className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed text-sm font-medium"
        >
          {loading ? "Loading..." : "Refresh"}
        </button>
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
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              className="bg-white dark:bg-zinc-800 rounded-lg shadow p-6 border border-zinc-200 dark:border-zinc-700 animate-pulse"
            >
              <div className="h-4 bg-zinc-200 dark:bg-zinc-700 rounded w-1/4 mb-2"></div>
              <div className="h-4 bg-zinc-200 dark:bg-zinc-700 rounded w-3/4 mb-2"></div>
              <div className="h-4 bg-zinc-200 dark:bg-zinc-700 rounded w-1/2"></div>
            </div>
          ))}
        </div>
      )}

      {/* Activity List */}
      {!loading && activities.length === 0 && (
        <div className="bg-white dark:bg-zinc-800 rounded-lg shadow p-8 border border-zinc-200 dark:border-zinc-700 text-center">
          <p className="text-zinc-500 dark:text-zinc-400">
            No activity yet. The agent has not posted anything.
          </p>
        </div>
      )}

      {!loading && activities.length > 0 && (
        <div className="space-y-4">
          {activities.map((item) => (
            <div
              key={item.id}
              className="bg-white dark:bg-zinc-800 rounded-lg shadow p-6 border border-zinc-200 dark:border-zinc-700"
            >
              <div className="flex items-start justify-between mb-2">
                <div className="flex items-center gap-2">
                  <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300">
                    {item.interaction_type}
                  </span>
                  <span className="text-sm text-zinc-600 dark:text-zinc-400">
                    r/{item.subreddit}
                  </span>
                </div>
                <span className="text-sm text-zinc-500 dark:text-zinc-500">
                  {formatDate(item.created_at)}
                </span>
              </div>

              <p className="text-zinc-900 dark:text-white mb-3">
                {truncate(item.content, 300)}
              </p>

              <div className="flex items-center gap-4">
                <a
                  href={getRedditUrl(item)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm text-blue-600 dark:text-blue-400 hover:underline"
                >
                  View on Reddit →
                </a>
                {item.metadata.karma !== undefined && (
                  <span className="text-sm text-zinc-600 dark:text-zinc-400">
                    {String(item.metadata.karma)} karma
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Pagination hint */}
      {!loading && activities.length > 0 && (
        <div className="mt-6 text-center text-sm text-zinc-500 dark:text-zinc-400">
          Showing {activities.length} most recent interactions
        </div>
      )}
    </div>
  );
}
