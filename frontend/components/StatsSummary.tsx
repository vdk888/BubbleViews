"use client";

import { useEffect, useState } from "react";
import { apiClient, StatsResponse } from "@/lib/api-client";

interface StatsSummaryProps {
  personaId: string | null;
}

export function StatsSummary({ personaId }: StatsSummaryProps) {
  const [stats, setStats] = useState<StatsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!personaId) {
      setLoading(false);
      return;
    }

    loadStats();
  }, [personaId]);

  const loadStats = async () => {
    if (!personaId) return;

    try {
      setLoading(true);
      const data = await apiClient.getStats(personaId);
      setStats(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load stats");
    } finally {
      setLoading(false);
    }
  };

  if (!personaId) {
    return (
      <div className="bg-white dark:bg-zinc-800 rounded-lg shadow p-6">
        <p className="text-zinc-500 dark:text-zinc-400">Select a persona to view stats</p>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {[1, 2, 3].map((i) => (
          <div key={i} className="bg-white dark:bg-zinc-800 rounded-lg shadow p-6 animate-pulse">
            <div className="h-4 bg-zinc-200 dark:bg-zinc-700 rounded w-1/2 mb-2"></div>
            <div className="h-8 bg-zinc-200 dark:bg-zinc-700 rounded w-1/3"></div>
          </div>
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
        <p className="text-red-800 dark:text-red-200">{error}</p>
        <button
          onClick={loadStats}
          className="mt-2 text-sm text-red-600 dark:text-red-400 hover:underline"
        >
          Retry
        </button>
      </div>
    );
  }

  if (!stats) return null;

  const statCards = [
    {
      label: "Total Interactions",
      value: stats.interactions,
      description: "Comments and posts made",
      icon: "💬",
    },
    {
      label: "Pending Posts",
      value: stats.pending_posts,
      description: "Awaiting moderation",
      icon: "⏳",
    },
    {
      label: "Belief Updates",
      value: stats.belief_updates,
      description: "Stance changes recorded",
      icon: "🧠",
    },
  ];

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
      {statCards.map((stat) => (
        <div
          key={stat.label}
          className="bg-white dark:bg-zinc-800 rounded-lg shadow p-6 border border-zinc-200 dark:border-zinc-700"
        >
          <div className="flex items-center justify-between mb-2">
            <p className="text-sm font-medium text-zinc-600 dark:text-zinc-400">
              {stat.label}
            </p>
            <span className="text-2xl">{stat.icon}</span>
          </div>
          <p className="text-3xl font-semibold text-zinc-900 dark:text-white mb-1">
            {stat.value.toLocaleString()}
          </p>
          <p className="text-xs text-zinc-500 dark:text-zinc-400">
            {stat.description}
          </p>
        </div>
      ))}
    </div>
  );
}
