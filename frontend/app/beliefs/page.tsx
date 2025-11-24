"use client";

import { useEffect, useState } from "react";
import { usePersona } from "@/hooks/usePersona";
import { apiClient, BeliefGraphResponse, BeliefNode, BeliefHistoryResponse } from "@/lib/api-client";
import { BeliefGraphViz } from "@/components/BeliefGraphViz";

export default function BeliefsPage() {
  const { selectedPersonaId } = usePersona();
  const [graphData, setGraphData] = useState<BeliefGraphResponse | null>(null);
  const [selectedBelief, setSelectedBelief] = useState<BeliefNode | null>(null);
  const [beliefHistory, setBeliefHistory] = useState<BeliefHistoryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);

  useEffect(() => {
    if (selectedPersonaId) {
      loadGraph();
    }
  }, [selectedPersonaId]);

  useEffect(() => {
    if (selectedBelief && selectedPersonaId) {
      loadHistory(selectedBelief.id);
    } else {
      setBeliefHistory(null);
    }
  }, [selectedBelief, selectedPersonaId]);

  const loadGraph = async () => {
    if (!selectedPersonaId) return;

    try {
      setLoading(true);
      const data = await apiClient.getBeliefGraph(selectedPersonaId);
      setGraphData(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load belief graph");
    } finally {
      setLoading(false);
    }
  };

  const loadHistory = async (beliefId: string) => {
    if (!selectedPersonaId) return;

    try {
      setHistoryLoading(true);
      const data = await apiClient.getBeliefHistory(beliefId, selectedPersonaId);
      setBeliefHistory(data);
    } catch (err) {
      console.error("Failed to load history:", err);
    } finally {
      setHistoryLoading(false);
    }
  };

  const handleNodeClick = (node: BeliefNode) => setSelectedBelief(node);
  const handleCloseDetail = () => {
    setSelectedBelief(null);
    setBeliefHistory(null);
  };

  const formatDate = (dateString: string | null) => {
    if (!dateString) return "Unknown";
    const date = new Date(dateString);
    return new Intl.DateTimeFormat("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }).format(date);
  };

  if (!selectedPersonaId) {
    return (
      <div className="page-shell">
        <div className="card p-4 bg-[var(--card)]">
          <p className="muted">Selectionnez une persona pour afficher le graphe de croyances.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="page-shell">
      <div className="mb-6">
        <h1>Belief Graph</h1>
        <p className="muted max-w-2xl">
          Visualisation interactive et transparente du systeme de croyances de l'agent.
        </p>
      </div>

      {error && (
        <div className="border border-red-200 bg-red-50 rounded-lg p-4 mb-6">
          <p className="text-red-800">{error}</p>
          <button onClick={loadGraph} className="mt-2 text-sm text-red-600 hover:underline">
            Retry
          </button>
        </div>
      )}

      {loading && (
        <div className="card p-8 text-center">
          <div className="animate-pulse h-96 bg-[var(--card)] rounded"></div>
          <p className="muted mt-4">Chargement du graphe...</p>
        </div>
      )}

      {!loading && graphData && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2">
            <div className="card p-6">
              {graphData.nodes.length === 0 ? (
                <div className="text-center py-12">
                  <p className="muted">
                    Aucune croyance pour le moment. L'agent n'a pas encore forme de position.
                  </p>
                </div>
              ) : (
                <BeliefGraphViz nodes={graphData.nodes} edges={graphData.edges} onNodeClick={handleNodeClick} />
              )}
            </div>
          </div>

          <div className="lg:col-span-1">
            {selectedBelief ? (
              <div className="card p-6 space-y-4">
                <div className="flex items-start justify-between">
                  <h2 className="text-lg font-semibold">Belief Details</h2>
                  <button
                    onClick={handleCloseDetail}
                    className="text-[var(--text-secondary)] hover:text-[var(--primary)]"
                  >
                    x
                  </button>
                </div>

                <div>
                  <h3 className="text-sm font-semibold text-[var(--text-secondary)] mb-1">Title</h3>
                  <p className="text-[var(--primary)]">{selectedBelief.title}</p>
                </div>

                <div>
                  <h3 className="text-sm font-semibold text-[var(--text-secondary)] mb-1">Summary</h3>
                  <p className="text-sm muted">{selectedBelief.summary}</p>
                </div>

                <div>
                  <h3 className="text-sm font-semibold text-[var(--text-secondary)] mb-2">Confidence</h3>
                  <div className="flex items-center gap-2">
                    <div className="flex-1 h-2 bg-[var(--card)] rounded-full overflow-hidden">
                      <div
                        className="h-full bg-[var(--primary)]"
                        style={{ width: `${(selectedBelief.confidence || 0) * 100}%` }}
                      ></div>
                    </div>
                    <span className="text-sm font-semibold text-[var(--primary)]">
                      {((selectedBelief.confidence || 0) * 100).toFixed(0)}%
                    </span>
                  </div>
                </div>

                {selectedBelief.tags && selectedBelief.tags.length > 0 && (
                  <div>
                    <h3 className="text-sm font-semibold text-[var(--text-secondary)] mb-2">Tags</h3>
                    <div className="flex flex-wrap gap-2">
                      {selectedBelief.tags.map((tag) => (
                        <span key={tag} className="chip text-xs">
                          {tag}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {historyLoading && <p className="text-sm muted">Chargement de l'historique...</p>}

                {beliefHistory && (
                  <>
                    <div>
                      <h3 className="text-sm font-semibold text-[var(--text-secondary)] mb-2">
                        Stance History ({beliefHistory.stances.length})
                      </h3>
                      <div className="space-y-2 max-h-48 overflow-y-auto">
                        {beliefHistory.stances.map((stance) => (
                          <div key={stance.id} className="p-2 bg-[var(--card)] rounded border border-[var(--border)]">
                            <div className="flex items-center justify-between mb-1 text-xs font-semibold">
                              <span>{stance.status}</span>
                              <span className="text-[var(--text-secondary)]">{stance.confidence?.toFixed(2)}</span>
                            </div>
                            <p className="text-xs muted">
                              {stance.text.substring(0, 100)}
                              {stance.text.length > 100 ? "..." : ""}
                            </p>
                            <p className="text-[var(--text-secondary)] text-xs mt-1">
                              {formatDate(stance.created_at)}
                            </p>
                          </div>
                        ))}
                      </div>
                    </div>

                    {beliefHistory.evidence.length > 0 && (
                      <div>
                        <h3 className="text-sm font-semibold text-[var(--text-secondary)] mb-2">
                          Evidence ({beliefHistory.evidence.length})
                        </h3>
                        <div className="space-y-1 max-h-32 overflow-y-auto">
                          {beliefHistory.evidence.map((ev) => (
                            <div key={ev.id} className="text-xs p-2 bg-[var(--card)] rounded">
                              <span className="font-semibold">{ev.source_type}</span>
                              {ev.strength && <span className="ml-2 text-[var(--text-secondary)]">({ev.strength})</span>}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </>
                )}
              </div>
            ) : (
              <div className="card p-6 text-center">
                <p className="muted">Cliquez sur un noeud pour afficher le detail.</p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
