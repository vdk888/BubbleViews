"use client";

import { useState, useEffect, useCallback } from "react";
import { apiClient } from "@/lib/api-client";

interface AgentStatus {
  persona_id: string;
  status: string;
  started_at: string | null;
  last_activity: string | null;
  error_message: string | null;
  cycle_count: number;
}

interface AgentControlPanelProps {
  personaId: string | null;
}

export function AgentControlPanel({ personaId }: AgentControlPanelProps) {
  const [status, setStatus] = useState<AgentStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchStatus = useCallback(async () => {
    if (!personaId) return;

    try {
      setLoading(true);
      const data = await apiClient.getAgentStatus(personaId);
      setStatus(data);
      setError(null);
    } catch (err) {
      // Agent might not have been started yet - that's OK
      setStatus({
        persona_id: personaId,
        status: "not_running",
        started_at: null,
        last_activity: null,
        error_message: null,
        cycle_count: 0,
      });
    } finally {
      setLoading(false);
    }
  }, [personaId]);

  useEffect(() => {
    fetchStatus();
    // Poll status every 30 seconds when agent is running
    const interval = setInterval(fetchStatus, 30000);
    return () => clearInterval(interval);
  }, [fetchStatus]);

  const handleToggle = async () => {
    if (!personaId || actionLoading) return;

    try {
      setActionLoading(true);
      setError(null);

      if (status?.status === "running") {
        await apiClient.stopAgent(personaId);
      } else {
        await apiClient.startAgent(personaId);
      }

      // Refetch status after action
      await fetchStatus();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Action failed");
    } finally {
      setActionLoading(false);
    }
  };

  const formatDateTime = (dateString: string | null) => {
    if (!dateString) return "-";
    const date = new Date(dateString);
    return new Intl.DateTimeFormat("fr-FR", {
      day: "2-digit",
      month: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    }).format(date);
  };

  const formatDuration = (startedAt: string | null) => {
    if (!startedAt) return "-";
    const start = new Date(startedAt);
    const now = new Date();
    const diffMs = now.getTime() - start.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMins / 60);
    const diffDays = Math.floor(diffHours / 24);

    if (diffDays > 0) return `${diffDays}j ${diffHours % 24}h`;
    if (diffHours > 0) return `${diffHours}h ${diffMins % 60}m`;
    return `${diffMins}m`;
  };

  const isRunning = status?.status === "running";
  const hasError = status?.status === "error";

  if (!personaId) {
    return (
      <div className="card glass shadow-strong p-6">
        <p className="muted text-center">Selectionnez une persona</p>
      </div>
    );
  }

  return (
    <div className="card glass shadow-strong p-6">
      {/* Header with status indicator */}
      <div className="flex items-center justify-between mb-4">
        <p className="text-sm font-semibold text-[var(--text-secondary)]">Agent</p>
        <span
          className={`inline-flex items-center gap-2 text-sm font-semibold ${
            isRunning
              ? "text-green-600"
              : hasError
              ? "text-red-600"
              : "text-[var(--text-secondary)]"
          }`}
        >
          <span
            className={`h-2.5 w-2.5 rounded-full ${
              isRunning
                ? "bg-green-500 animate-pulse"
                : hasError
                ? "bg-red-500"
                : "bg-gray-400"
            }`}
          ></span>
          {isRunning ? "En cours" : hasError ? "Erreur" : "Arrete"}
        </span>
      </div>

      {/* Toggle Button */}
      <div className="mb-4">
        <button
          onClick={handleToggle}
          disabled={loading || actionLoading}
          className={`w-full py-3 px-4 rounded-lg font-semibold text-white transition-all duration-200 ${
            isRunning
              ? "bg-red-600 hover:bg-red-700"
              : "bg-green-600 hover:bg-green-700"
          } disabled:opacity-50 disabled:cursor-not-allowed`}
        >
          {actionLoading ? (
            <span className="flex items-center justify-center gap-2">
              <svg
                className="animate-spin h-4 w-4"
                xmlns="http://www.w3.org/2000/svg"
                fill="none"
                viewBox="0 0 24 24"
              >
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                ></circle>
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                ></path>
              </svg>
              {isRunning ? "Arret..." : "Demarrage..."}
            </span>
          ) : isRunning ? (
            "Arreter l'agent"
          ) : (
            "Demarrer l'agent"
          )}
        </button>
      </div>

      {/* Error message */}
      {(error || status?.error_message) && (
        <div className="mb-4 p-3 rounded-lg bg-red-100 border border-red-200">
          <p className="text-sm text-red-700">{error || status?.error_message}</p>
        </div>
      )}

      {/* Stats Grid */}
      <div className="grid grid-cols-2 gap-3">
        <div className="p-3 rounded-lg bg-[var(--background)]">
          <p className="text-xs text-[var(--text-secondary)] mb-1">Cycles</p>
          <p className="text-lg font-bold text-[var(--primary)]">
            {status?.cycle_count ?? 0}
          </p>
        </div>
        <div className="p-3 rounded-lg bg-[var(--background)]">
          <p className="text-xs text-[var(--text-secondary)] mb-1">Uptime</p>
          <p className="text-lg font-bold text-[var(--primary)]">
            {isRunning ? formatDuration(status?.started_at ?? null) : "-"}
          </p>
        </div>
        <div className="p-3 rounded-lg bg-[var(--background)]">
          <p className="text-xs text-[var(--text-secondary)] mb-1">Demarre</p>
          <p className="text-sm font-semibold text-[var(--text-primary)]">
            {formatDateTime(status?.started_at ?? null)}
          </p>
        </div>
        <div className="p-3 rounded-lg bg-[var(--background)]">
          <p className="text-xs text-[var(--text-secondary)] mb-1">Activite</p>
          <p className="text-sm font-semibold text-[var(--text-primary)]">
            {formatDateTime(status?.last_activity ?? null)}
          </p>
        </div>
      </div>
    </div>
  );
}
