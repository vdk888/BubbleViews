"use client";

import { useState, useEffect, useCallback } from "react";
import { apiClient } from "@/lib/api-client";

interface AgentStatus {
  persona_id: string;
  persona_name: string | null;
  status: string;
  started_at: string | null;
  last_activity: string | null;
  error_message: string | null;
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
    try {
      setLoading(true);
      // Use systemd status (global, not per-persona)
      const data = await apiClient.getSystemdAgentStatus();
      setStatus({
        persona_id: data.persona_id || "",
        persona_name: data.persona_name || null,
        status: data.status,
        started_at: null,
        last_activity: null,
        error_message: data.status === "failed" ? data.message : null,
      });
      setError(null);
    } catch (err) {
      // Agent might not have been started yet - that's OK
      setStatus({
        persona_id: personaId || "",
        persona_name: null,
        status: "stopped",
        started_at: null,
        last_activity: null,
        error_message: null,
      });
    } finally {
      setLoading(false);
    }
  }, [personaId]);

  useEffect(() => {
    fetchStatus();
    // Poll status every 5 seconds
    const interval = setInterval(fetchStatus, 5000);
    return () => clearInterval(interval);
  }, [fetchStatus]);

  const handleToggle = async () => {
    if (!personaId || actionLoading) return;

    try {
      setActionLoading(true);
      setError(null);

      if (status?.status === "running") {
        await apiClient.stopSystemdAgent();
      } else {
        const result = await apiClient.startSystemdAgent(personaId);
        if (result.status === "failed") {
          setError(result.message);
        }
      }

      // Refetch status after action
      await fetchStatus();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Action failed");
    } finally {
      setActionLoading(false);
    }
  };

  const isRunning = status?.status === "running";
  const hasError = status?.status === "error" || status?.status === "failed";

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
        <div>
          <p className="text-sm font-semibold text-[var(--text-secondary)]">Agent</p>
          {isRunning && status?.persona_name && (
            <p className="text-xs text-[var(--text-secondary)]">
              Running as: {status.persona_name}
            </p>
          )}
        </div>
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
          <p className="text-xs text-[var(--text-secondary)] mb-1">Status</p>
          <p className="text-lg font-bold text-[var(--primary)]">
            {isRunning ? "Active" : hasError ? "Failed" : "Stopped"}
          </p>
        </div>
        <div className="p-3 rounded-lg bg-[var(--background)]">
          <p className="text-xs text-[var(--text-secondary)] mb-1">Persona</p>
          <p className="text-sm font-bold text-[var(--primary)] truncate">
            {status?.persona_name || "-"}
          </p>
        </div>
      </div>
    </div>
  );
}
