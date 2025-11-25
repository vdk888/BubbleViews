"use client";

import { useEffect, useState } from "react";
import { usePersona } from "@/hooks/usePersona";
import { apiClient, BeliefGraphResponse, BeliefNode, BeliefHistoryResponse, RelationshipSuggestion } from "@/lib/api-client";
import { BeliefGraphViz } from "@/components/BeliefGraphViz";
import { BeliefListView } from "@/components/BeliefListView";

export default function BeliefsPage() {
  const { selectedPersonaId } = usePersona();
  const [graphData, setGraphData] = useState<BeliefGraphResponse | null>(null);
  const [selectedBelief, setSelectedBelief] = useState<BeliefNode | null>(null);
  const [beliefHistory, setBeliefHistory] = useState<BeliefHistoryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [editMode, setEditMode] = useState(false);
  const [editConfidence, setEditConfidence] = useState<number | null>(null);
  const [updating, setUpdating] = useState(false);
  const [updateMessage, setUpdateMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  // View mode toggle: "graph" or "list"
  const [viewMode, setViewMode] = useState<"graph" | "list">("graph");

  // Relationship suggestions state (for Phase 4 integration)
  const [showSuggestionModal, setShowSuggestionModal] = useState(false);
  const [suggestedRelationships, setSuggestedRelationships] = useState<RelationshipSuggestion[]>([]);
  const [suggestingRelationships, setSuggestingRelationships] = useState(false);

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
    setEditMode(false);
    setEditConfidence(null);
    setUpdateMessage(null);
  };

  const handleCloseDetail = () => {
    setSelectedBelief(null);
    setBeliefHistory(null);
    setEditMode(false);
    setEditConfidence(null);
    setUpdateMessage(null);
  };

  const handleNudge = async (direction: "increase" | "decrease") => {
    if (!selectedBelief || !selectedPersonaId) return;

    try {
      setUpdating(true);
      setUpdateMessage(null);

      await apiClient.nudgeBelief(selectedBelief.id, {
        persona_id: selectedPersonaId,
        direction,
        amount: 0.05,
        reason: `Manual ${direction} via dashboard`,
      });

      // Reload graph and history
      await loadGraph();
      await loadHistory(selectedBelief.id);
      setUpdateMessage({ type: "success", text: `Confidence ${direction}d successfully` });
      setTimeout(() => setUpdateMessage(null), 3000);
    } catch (err) {
      setUpdateMessage({
        type: "error",
        text: err instanceof Error ? err.message : "Failed to update belief",
      });
    } finally {
      setUpdating(false);
    }
  };

  const handleSaveConfidence = async () => {
    if (!selectedBelief || !selectedPersonaId || editConfidence === null) return;

    try {
      setUpdating(true);
      setUpdateMessage(null);

      await apiClient.updateBelief(selectedBelief.id, {
        persona_id: selectedPersonaId,
        confidence: editConfidence,
        rationale: "Manual confidence update via dashboard",
      });

      // Reload graph and history
      await loadGraph();
      await loadHistory(selectedBelief.id);
      setEditMode(false);
      setEditConfidence(null);
      setUpdateMessage({ type: "success", text: "Belief updated successfully" });
      setTimeout(() => setUpdateMessage(null), 3000);
    } catch (err) {
      setUpdateMessage({
        type: "error",
        text: err instanceof Error ? err.message : "Failed to update belief",
      });
    } finally {
      setUpdating(false);
    }
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

  // Handler for suggesting relationships for a belief
  const handleSuggestRelationships = async () => {
    if (!selectedBelief || !selectedPersonaId) return;

    try {
      setSuggestingRelationships(true);
      setUpdateMessage(null);
      const suggestions = await apiClient.suggestRelationships(
        selectedBelief.id,
        selectedPersonaId
      );
      setSuggestedRelationships(suggestions);
      setShowSuggestionModal(true);
    } catch (err) {
      setUpdateMessage({
        type: "error",
        text: err instanceof Error ? err.message : "Failed to get relationship suggestions",
      });
    } finally {
      setSuggestingRelationships(false);
    }
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
        <div className="flex items-start justify-between flex-wrap gap-4">
          <div>
            <h1>Belief Graph</h1>
            <p className="muted max-w-2xl">
              Visualisation interactive et transparente du systeme de croyances de l'agent.
            </p>
          </div>
          <div className="flex gap-2 items-center">
            <button
              onClick={() => setViewMode("graph")}
              className={`px-4 py-2 text-sm font-semibold rounded-lg transition-colors ${
                viewMode === "graph"
                  ? "bg-[var(--primary)] text-white"
                  : "bg-[var(--card)] text-[var(--text-secondary)] hover:bg-[var(--border)]"
              }`}
            >
              Graph View
            </button>
            <button
              onClick={() => setViewMode("list")}
              className={`px-4 py-2 text-sm font-semibold rounded-lg transition-colors ${
                viewMode === "list"
                  ? "bg-[var(--primary)] text-white"
                  : "bg-[var(--card)] text-[var(--text-secondary)] hover:bg-[var(--border)]"
              }`}
            >
              List View
            </button>
          </div>
        </div>
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
            {viewMode === "graph" ? (
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
            ) : (
              <BeliefListView beliefs={graphData.nodes} onBeliefClick={handleNodeClick} />
            )}
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

                {updateMessage && (
                  <div
                    className={`p-3 rounded text-sm font-semibold ${
                      updateMessage.type === "success"
                        ? "bg-green-100 text-green-700"
                        : "bg-red-100 text-red-700"
                    }`}
                  >
                    {updateMessage.text}
                  </div>
                )}

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
                  {!editMode ? (
                    <>
                      <div className="flex items-center gap-2 mb-3">
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
                      <div className="flex gap-2">
                        <button
                          onClick={() => handleNudge("decrease")}
                          disabled={updating}
                          className="flex-1 px-2 py-1 text-xs font-semibold rounded bg-red-100 text-red-700 hover:bg-red-200 disabled:opacity-50"
                        >
                          - Less confident
                        </button>
                        <button
                          onClick={() => handleNudge("increase")}
                          disabled={updating}
                          className="flex-1 px-2 py-1 text-xs font-semibold rounded bg-green-100 text-green-700 hover:bg-green-200 disabled:opacity-50"
                        >
                          + More confident
                        </button>
                        <button
                          onClick={() => {
                            setEditMode(true);
                            setEditConfidence(selectedBelief.confidence || 0.5);
                          }}
                          className="flex-1 px-2 py-1 text-xs font-semibold rounded bg-blue-100 text-blue-700 hover:bg-blue-200"
                        >
                          Edit
                        </button>
                      </div>
                    </>
                  ) : (
                    <>
                      <div className="space-y-2">
                        <input
                          type="range"
                          min="0"
                          max="1"
                          step="0.01"
                          value={editConfidence || 0}
                          onChange={(e) => setEditConfidence(parseFloat(e.target.value))}
                          className="w-full"
                          disabled={updating}
                        />
                        <div className="flex items-center justify-between">
                          <span className="text-sm font-semibold text-[var(--primary)]">
                            {((editConfidence || 0) * 100).toFixed(0)}%
                          </span>
                        </div>
                      </div>
                      <div className="flex gap-2 mt-3">
                        <button
                          onClick={handleSaveConfidence}
                          disabled={updating || editConfidence === null}
                          className="flex-1 px-2 py-1 text-xs font-semibold rounded bg-green-600 text-white hover:bg-green-700 disabled:opacity-50"
                        >
                          Save
                        </button>
                        <button
                          onClick={() => {
                            setEditMode(false);
                            setEditConfidence(null);
                          }}
                          disabled={updating}
                          className="flex-1 px-2 py-1 text-xs font-semibold rounded bg-gray-300 text-gray-700 hover:bg-gray-400 disabled:opacity-50"
                        >
                          Cancel
                        </button>
                      </div>
                    </>
                  )}
                </div>

                {/* Suggest Relationships Button */}
                <div>
                  <button
                    onClick={handleSuggestRelationships}
                    disabled={updating || suggestingRelationships}
                    className="w-full px-3 py-2 rounded-lg bg-purple-600 text-white text-sm font-semibold hover:bg-purple-700 disabled:opacity-50 transition-colors"
                  >
                    {suggestingRelationships ? "Analyzing..." : "Suggest Relationships"}
                  </button>
                  <p className="text-xs text-[var(--text-secondary)] mt-1">
                    Use AI to find connections with other beliefs
                  </p>
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
