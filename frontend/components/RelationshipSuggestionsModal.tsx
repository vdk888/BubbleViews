"use client";

import { useState, useCallback } from "react";
import { apiClient, RelationshipSuggestion } from "@/lib/api-client";

/**
 * Relationship type configuration
 */
interface RelationTypeConfig {
  icon: string;
  label: string;
  colorClass: string;
  bgClass: string;
}

const RELATION_TYPES: Record<string, RelationTypeConfig> = {
  supports: {
    icon: "\u2713", // checkmark
    label: "Supports",
    colorClass: "text-green-700",
    bgClass: "bg-green-100",
  },
  contradicts: {
    icon: "\u2717", // X mark
    label: "Contradicts",
    colorClass: "text-red-700",
    bgClass: "bg-red-100",
  },
  depends_on: {
    icon: "\u2192", // arrow right
    label: "Depends On",
    colorClass: "text-blue-700",
    bgClass: "bg-blue-100",
  },
  evidence_for: {
    icon: "\u25C7", // diamond
    label: "Evidence For",
    colorClass: "text-purple-700",
    bgClass: "bg-purple-100",
  },
};

/**
 * Get relation type configuration (with fallback for unknown types)
 */
function getRelationConfig(relation: string): RelationTypeConfig {
  return (
    RELATION_TYPES[relation] || {
      icon: "\u2022", // bullet
      label: relation.replace(/_/g, " "),
      colorClass: "text-gray-700",
      bgClass: "bg-gray-100",
    }
  );
}

/**
 * Selection state for a suggestion
 */
interface SuggestionSelection {
  id: string;
  selected: boolean;
}

/**
 * Result of creating a relationship
 */
interface CreateResult {
  suggestion: RelationshipSuggestion;
  success: boolean;
  error?: string;
}

/**
 * RelationshipSuggestionsModal Props
 */
interface RelationshipSuggestionsModalProps {
  isOpen: boolean;
  suggestions: RelationshipSuggestion[];
  personaId: string;
  sourceBeliefId: string;
  onClose: () => void;
  onRelationshipsCreated: () => void;
}

/**
 * RelationshipSuggestionsModal Component
 *
 * A reusable modal for reviewing and approving AI-suggested belief relationships.
 *
 * Features:
 * - Display list of AI-suggested relationships with checkboxes
 * - Each suggestion shows target belief, relation type, weight, and reasoning
 * - Select All / Deselect All functionality
 * - Creates only checked relationships
 * - Handles partial failures gracefully
 * - Visual feedback during creation
 */
export function RelationshipSuggestionsModal({
  isOpen,
  suggestions,
  personaId,
  sourceBeliefId,
  onClose,
  onRelationshipsCreated,
}: RelationshipSuggestionsModalProps) {
  // Selection state - all suggestions selected by default
  const [selections, setSelections] = useState<Map<string, boolean>>(() => {
    const map = new Map<string, boolean>();
    suggestions.forEach((s) => map.set(s.target_belief_id, true));
    return map;
  });

  // UI state
  const [creating, setCreating] = useState(false);
  const [results, setResults] = useState<CreateResult[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Reset state when suggestions change
  const resetSelections = useCallback(() => {
    const map = new Map<string, boolean>();
    suggestions.forEach((s) => map.set(s.target_belief_id, true));
    setSelections(map);
    setResults(null);
    setError(null);
  }, [suggestions]);

  // Update selections when suggestions prop changes
  if (isOpen && suggestions.length > 0 && selections.size !== suggestions.length) {
    resetSelections();
  }

  /**
   * Toggle selection for a single suggestion
   */
  const toggleSelection = useCallback((targetBeliefId: string) => {
    setSelections((prev) => {
      const newMap = new Map(prev);
      newMap.set(targetBeliefId, !prev.get(targetBeliefId));
      return newMap;
    });
  }, []);

  /**
   * Select all suggestions
   */
  const selectAll = useCallback(() => {
    setSelections((prev) => {
      const newMap = new Map(prev);
      suggestions.forEach((s) => newMap.set(s.target_belief_id, true));
      return newMap;
    });
  }, [suggestions]);

  /**
   * Deselect all suggestions
   */
  const deselectAll = useCallback(() => {
    setSelections((prev) => {
      const newMap = new Map(prev);
      suggestions.forEach((s) => newMap.set(s.target_belief_id, false));
      return newMap;
    });
  }, [suggestions]);

  /**
   * Count of selected suggestions
   */
  const selectedCount = Array.from(selections.values()).filter(Boolean).length;

  /**
   * Handle creating relationships for selected suggestions
   */
  const handleCreateRelationships = useCallback(async () => {
    const selectedSuggestions = suggestions.filter(
      (s) => selections.get(s.target_belief_id)
    );

    if (selectedSuggestions.length === 0) {
      setError("Please select at least one relationship to create.");
      return;
    }

    setCreating(true);
    setError(null);
    setResults(null);

    const createResults: CreateResult[] = [];

    // Create relationships one by one to handle partial failures
    for (const suggestion of selectedSuggestions) {
      try {
        await apiClient.createRelationship(sourceBeliefId, {
          persona_id: personaId,
          target_belief_id: suggestion.target_belief_id,
          relation: suggestion.relation,
          weight: suggestion.weight || 0.5,
        });
        createResults.push({ suggestion, success: true });
      } catch (err) {
        const errorMessage =
          err instanceof Error ? err.message : "Unknown error";
        createResults.push({
          suggestion,
          success: false,
          error: errorMessage,
        });
      }
    }

    setCreating(false);
    setResults(createResults);

    const successCount = createResults.filter((r) => r.success).length;
    const failCount = createResults.filter((r) => !r.success).length;

    if (failCount === 0) {
      // All succeeded - close modal and notify parent
      setTimeout(() => {
        onRelationshipsCreated();
      }, 1000); // Brief delay to show success message
    } else if (successCount > 0) {
      // Partial success - show results, let user decide
      setError(
        `Created ${successCount} of ${selectedSuggestions.length} relationships. ${failCount} failed.`
      );
    } else {
      // All failed
      setError("Failed to create relationships. Please try again.");
    }
  }, [suggestions, selections, sourceBeliefId, personaId, onRelationshipsCreated]);

  /**
   * Handle modal close
   */
  const handleClose = useCallback(() => {
    if (!creating) {
      setResults(null);
      setError(null);
      onClose();
    }
  }, [creating, onClose]);

  /**
   * Handle backdrop click
   */
  const handleBackdropClick = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      if (e.target === e.currentTarget) {
        handleClose();
      }
    },
    [handleClose]
  );

  // Don't render if not open or no suggestions
  if (!isOpen) return null;

  // Success state - all relationships created
  const allSuccess =
    results !== null && results.every((r) => r.success) && results.length > 0;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={handleBackdropClick}
      role="dialog"
      aria-modal="true"
      aria-labelledby="suggestions-modal-title"
    >
      <div
        className="bg-white rounded-xl shadow-lg w-full max-w-[600px] mx-4 max-h-[90vh] overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--border)]">
          <div>
            <h2
              id="suggestions-modal-title"
              className="text-lg font-semibold text-[var(--primary)]"
            >
              Suggested Relationships
            </h2>
            <p className="text-sm text-[var(--text-secondary)] mt-0.5">
              AI found {suggestions.length} potential connection
              {suggestions.length !== 1 ? "s" : ""}
            </p>
          </div>
          <button
            onClick={handleClose}
            disabled={creating}
            className="text-[var(--text-secondary)] hover:text-[var(--primary)] transition-colors text-xl leading-none disabled:opacity-50"
            aria-label="Close modal"
          >
            x
          </button>
        </div>

        {/* Success Message */}
        {allSuccess && (
          <div className="px-6 py-4 bg-green-50 border-b border-green-200">
            <div className="flex items-center gap-2 text-green-700">
              <svg
                className="w-5 h-5"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M5 13l4 4L19 7"
                />
              </svg>
              <span className="font-semibold">
                {results.length} relationship{results.length !== 1 ? "s" : ""}{" "}
                created successfully!
              </span>
            </div>
          </div>
        )}

        {/* Error Message */}
        {error && !allSuccess && (
          <div className="px-6 py-3 bg-red-50 border-b border-red-200">
            <p className="text-sm text-red-700">{error}</p>
          </div>
        )}

        {/* Selection Controls */}
        {!allSuccess && (
          <div className="px-6 py-3 bg-gray-50 border-b border-[var(--border)] flex items-center justify-between">
            <span className="text-sm text-[var(--text-secondary)]">
              {selectedCount} of {suggestions.length} selected
            </span>
            <div className="flex gap-2">
              <button
                onClick={selectAll}
                disabled={creating || selectedCount === suggestions.length}
                className="text-xs font-medium text-[var(--primary)] hover:underline disabled:opacity-50 disabled:no-underline"
              >
                Select All
              </button>
              <span className="text-[var(--text-secondary)]">|</span>
              <button
                onClick={deselectAll}
                disabled={creating || selectedCount === 0}
                className="text-xs font-medium text-[var(--primary)] hover:underline disabled:opacity-50 disabled:no-underline"
              >
                Deselect All
              </button>
            </div>
          </div>
        )}

        {/* Suggestions List */}
        <div className="flex-1 overflow-y-auto px-6 py-4">
          {suggestions.length === 0 ? (
            <div className="text-center py-8">
              <p className="text-[var(--text-secondary)]">
                No relationship suggestions found.
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {suggestions.map((suggestion) => {
                const relationConfig = getRelationConfig(suggestion.relation);
                const isSelected = selections.get(suggestion.target_belief_id);
                const result = results?.find(
                  (r) => r.suggestion.target_belief_id === suggestion.target_belief_id
                );

                return (
                  <div
                    key={suggestion.target_belief_id}
                    className={`border rounded-lg p-4 transition-colors ${
                      result?.success
                        ? "border-green-200 bg-green-50"
                        : result?.success === false
                        ? "border-red-200 bg-red-50"
                        : isSelected
                        ? "border-[var(--primary)]/30 bg-[var(--primary)]/5"
                        : "border-[var(--border)] hover:border-[var(--border-hover)]"
                    }`}
                  >
                    <div className="flex items-start gap-3">
                      {/* Checkbox */}
                      {!allSuccess && (
                        <input
                          type="checkbox"
                          checked={isSelected || false}
                          onChange={() => toggleSelection(suggestion.target_belief_id)}
                          disabled={creating || result !== undefined}
                          className="mt-1 w-4 h-4 text-[var(--primary)] border-[var(--border)] rounded focus:ring-[var(--primary)]/20 disabled:opacity-50"
                          aria-label={`Select relationship with ${suggestion.target_belief_title}`}
                        />
                      )}

                      {/* Content */}
                      <div className="flex-1 min-w-0">
                        {/* Target Belief Title */}
                        <h3 className="font-semibold text-[var(--primary)] truncate">
                          {suggestion.target_belief_title}
                        </h3>

                        {/* Relation Type and Weight */}
                        <div className="flex items-center gap-3 mt-2">
                          {/* Relation Type Badge */}
                          <span
                            className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-full text-xs font-semibold ${relationConfig.bgClass} ${relationConfig.colorClass}`}
                          >
                            <span className="text-sm">{relationConfig.icon}</span>
                            {relationConfig.label}
                          </span>

                          {/* Weight Bar */}
                          <div className="flex items-center gap-2 flex-1">
                            <div className="flex-1 h-2 bg-gray-200 rounded-full overflow-hidden max-w-[100px]">
                              <div
                                className={`h-full rounded-full transition-all ${
                                  suggestion.relation === "contradicts"
                                    ? "bg-red-500"
                                    : suggestion.relation === "supports"
                                    ? "bg-green-500"
                                    : suggestion.relation === "depends_on"
                                    ? "bg-blue-500"
                                    : "bg-purple-500"
                                }`}
                                style={{
                                  width: `${(suggestion.weight || 0.5) * 100}%`,
                                }}
                              />
                            </div>
                            <span className="text-xs text-[var(--text-secondary)] font-medium">
                              {Math.round((suggestion.weight || 0.5) * 100)}%
                            </span>
                          </div>
                        </div>

                        {/* Reasoning */}
                        <p className="text-sm text-[var(--text-secondary)] mt-2 leading-relaxed">
                          {suggestion.reasoning}
                        </p>

                        {/* Error for this item */}
                        {result?.success === false && result.error && (
                          <p className="text-xs text-red-600 mt-2">
                            Error: {result.error}
                          </p>
                        )}
                      </div>

                      {/* Status Icon */}
                      {result && (
                        <div className="flex-shrink-0">
                          {result.success ? (
                            <svg
                              className="w-5 h-5 text-green-600"
                              fill="none"
                              stroke="currentColor"
                              viewBox="0 0 24 24"
                            >
                              <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                strokeWidth={2}
                                d="M5 13l4 4L19 7"
                              />
                            </svg>
                          ) : (
                            <svg
                              className="w-5 h-5 text-red-600"
                              fill="none"
                              stroke="currentColor"
                              viewBox="0 0 24 24"
                            >
                              <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                strokeWidth={2}
                                d="M6 18L18 6M6 6l12 12"
                              />
                            </svg>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-3 px-6 py-4 border-t border-[var(--border)] bg-gray-50">
          {allSuccess ? (
            <button
              onClick={handleClose}
              className="px-4 py-2 text-sm font-semibold text-white bg-green-600 rounded-lg hover:bg-green-700 transition-colors"
            >
              Done
            </button>
          ) : (
            <>
              <button
                type="button"
                onClick={handleClose}
                disabled={creating}
                className="px-4 py-2 text-sm font-semibold text-[var(--text-secondary)] bg-white border border-[var(--border)] rounded-lg hover:bg-gray-50 transition-colors disabled:opacity-50"
              >
                Skip
              </button>
              <button
                type="button"
                onClick={handleCreateRelationships}
                disabled={creating || selectedCount === 0}
                className="px-4 py-2 text-sm font-semibold text-white bg-purple-600 rounded-lg hover:bg-purple-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
              >
                {creating && (
                  <svg
                    className="animate-spin h-4 w-4 text-white"
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
                )}
                {creating
                  ? "Creating..."
                  : `Create ${selectedCount} Relationship${
                      selectedCount !== 1 ? "s" : ""
                    }`}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
