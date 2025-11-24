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

  const handleNodeClick = (node: BeliefNode) => {
    setSelectedBelief(node);
  };

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
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg p-4">
          <p className="text-yellow-800 dark:text-yellow-200">
            Please select a persona to view belief graph
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="mb-6">
        <h1 className="text-3xl font-bold text-zinc-900 dark:text-white mb-2">
          Belief Graph
        </h1>
        <p className="text-zinc-600 dark:text-zinc-400">
          Interactive visualization of the agent's belief system
        </p>
      </div>

      {/* Error State */}
      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4 mb-6">
          <p className="text-red-800 dark:text-red-200">{error}</p>
          <button
            onClick={loadGraph}
            className="mt-2 text-sm text-red-600 dark:text-red-400 hover:underline"
          >
            Retry
          </button>
        </div>
      )}

      {/* Loading State */}
      {loading && (
        <div className="bg-white dark:bg-zinc-800 rounded-lg shadow p-8 border border-zinc-200 dark:border-zinc-700 text-center">
          <div className="animate-pulse">
            <div className="h-96 bg-zinc-200 dark:bg-zinc-700 rounded"></div>
          </div>
          <p className="mt-4 text-zinc-500 dark:text-zinc-400">Loading belief graph...</p>
        </div>
      )}

      {/* Graph Visualization */}
      {!loading && graphData && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2">
            <div className="bg-white dark:bg-zinc-800 rounded-lg shadow p-6 border border-zinc-200 dark:border-zinc-700">
              {graphData.nodes.length === 0 ? (
                <div className="text-center py-12">
                  <p className="text-zinc-500 dark:text-zinc-400">
                    No beliefs recorded yet. The agent has not formed any stances.
                  </p>
                </div>
              ) : (
                <BeliefGraphViz
                  nodes={graphData.nodes}
                  edges={graphData.edges}
                  onNodeClick={handleNodeClick}
                />
              )}
            </div>
          </div>

          <div className="lg:col-span-1">
            {selectedBelief ? (
              <div className="bg-white dark:bg-zinc-800 rounded-lg shadow p-6 border border-zinc-200 dark:border-zinc-700">
                <div className="flex items-start justify-between mb-4">
                  <h2 className="text-lg font-semibold text-zinc-900 dark:text-white">
                    Belief Details
                  </h2>
                  <button
                    onClick={handleCloseDetail}
                    className="text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200"
                  >
                    ✕
                  </button>
                </div>

                <div className="space-y-4">
                  <div>
                    <h3 className="text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-1">
                      Title
                    </h3>
                    <p className="text-zinc-900 dark:text-white">{selectedBelief.title}</p>
                  </div>

                  <div>
                    <h3 className="text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-1">
                      Summary
                    </h3>
                    <p className="text-sm text-zinc-600 dark:text-zinc-400">
                      {selectedBelief.summary}
                    </p>
                  </div>

                  <div>
                    <h3 className="text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-1">
                      Confidence
                    </h3>
                    <div className="flex items-center gap-2">
                      <div className="flex-1 h-2 bg-zinc-200 dark:bg-zinc-700 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-blue-500"
                          style={{ width: `${(selectedBelief.confidence || 0) * 100}%` }}
                        ></div>
                      </div>
                      <span className="text-sm font-medium text-zinc-900 dark:text-white">
                        {((selectedBelief.confidence || 0) * 100).toFixed(0)}%
                      </span>
                    </div>
                  </div>

                  {selectedBelief.tags && selectedBelief.tags.length > 0 && (
                    <div>
                      <h3 className="text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-1">
                        Tags
                      </h3>
                      <div className="flex flex-wrap gap-2">
                        {selectedBelief.tags.map((tag) => (
                          <span
                            key={tag}
                            className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300"
                          >
                            {tag}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {historyLoading && (
                    <div className="text-sm text-zinc-500 dark:text-zinc-400">
                      Loading history...
                    </div>
                  )}

                  {beliefHistory && (
                    <>
                      <div>
                        <h3 className="text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
                          Stance History ({beliefHistory.stances.length})
                        </h3>
                        <div className="space-y-2 max-h-48 overflow-y-auto">
                          {beliefHistory.stances.map((stance) => (
                            <div
                              key={stance.id}
                              className="text-xs p-2 bg-zinc-50 dark:bg-zinc-900 rounded border border-zinc-200 dark:border-zinc-700"
                            >
                              <div className="flex items-center justify-between mb-1">
                                <span className="font-medium">{stance.status}</span>
                                <span className="text-zinc-500">
                                  {stance.confidence?.toFixed(2)}
                                </span>
                              </div>
                              <p className="text-zinc-600 dark:text-zinc-400">
                                {stance.text.substring(0, 100)}
                                {stance.text.length > 100 ? "..." : ""}
                              </p>
                              <p className="text-zinc-500 dark:text-zinc-500 mt-1">
                                {formatDate(stance.created_at)}
                              </p>
                            </div>
                          ))}
                        </div>
                      </div>

                      {beliefHistory.evidence.length > 0 && (
                        <div>
                          <h3 className="text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
                            Evidence ({beliefHistory.evidence.length})
                          </h3>
                          <div className="space-y-1 max-h-32 overflow-y-auto">
                            {beliefHistory.evidence.map((ev) => (
                              <div
                                key={ev.id}
                                className="text-xs p-2 bg-zinc-50 dark:bg-zinc-900 rounded"
                              >
                                <span className="font-medium">{ev.source_type}</span>
                                {ev.strength && (
                                  <span className="ml-2 text-zinc-500">({ev.strength})</span>
                                )}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </>
                  )}

                  <div className="pt-4 border-t border-zinc-200 dark:border-zinc-700">
                    <button
                      className="w-full px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 text-sm font-medium"
                      onClick={() => alert("Edit functionality coming soon")}
                    >
                      Edit Belief
                    </button>
                  </div>
                </div>
              </div>
            ) : (
              <div className="bg-white dark:bg-zinc-800 rounded-lg shadow p-6 border border-zinc-200 dark:border-zinc-700 text-center">
                <p className="text-zinc-500 dark:text-zinc-400">
                  Click a node to view details
                </p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
