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
      <div className="card p-6">
        <p className="muted">Selectionnez une persona pour afficher les statistiques.</p>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {[1, 2, 3].map((i) => (
          <div key={i} className="card p-6 animate-pulse">
            <div className="h-4 bg-[var(--card)] rounded w-1/2 mb-2"></div>
            <div className="h-8 bg-[var(--card)] rounded w-1/3"></div>
          </div>
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="border border-red-200 bg-red-50 rounded-lg p-4">
        <p className="text-red-800">{error}</p>
        <button onClick={loadStats} className="mt-2 text-sm text-red-600 hover:underline">
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
      icon: "o",
    },
    {
      label: "Pending Posts",
      value: stats.pending_posts,
      description: "Awaiting moderation",
      icon: "()",
    },
    {
      label: "Belief Updates",
      value: stats.belief_updates,
      description: "Stance changes recorded",
      icon: "*",
    },
  ];

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
      {statCards.map((stat) => (
        <div
          key={stat.label}
          className="card p-6 transition-transform duration-300 ease-out hover:-translate-y-1 hover:shadow-strong"
        >
          <div className="flex items-center justify-between mb-2">
            <p className="text-sm font-semibold text-[var(--text-secondary)]">{stat.label}</p>
            <span className="text-xl text-[var(--primary)]">{stat.icon}</span>
          </div>
          <p className="text-3xl font-extrabold text-[var(--primary)] mb-1">
            {stat.value.toLocaleString()}
          </p>
          <p className="text-xs muted">{stat.description}</p>
        </div>
      ))}
    </div>
  );
}
