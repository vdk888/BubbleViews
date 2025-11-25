"use client";

import { useState, useMemo } from "react";
import { BeliefNode } from "@/lib/api-client";

interface BeliefListViewProps {
  beliefs: BeliefNode[];
  onBeliefClick: (belief: BeliefNode) => void;
}

type SortField = "title" | "confidence" | "created_at";
type SortDirection = "asc" | "desc";

/**
 * BeliefListView Component
 *
 * Displays beliefs in a sortable, filterable table format.
 * Features:
 * - Search by title/summary
 * - Filter by tags and confidence range
 * - Sort by title, confidence, or created date
 * - Click rows to view belief details
 */
export function BeliefListView({ beliefs, onBeliefClick }: BeliefListViewProps) {
  // Search and filter state
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [confidenceRange, setConfidenceRange] = useState<[number, number]>([0, 1]);

  // Sort state
  const [sortBy, setSortBy] = useState<SortField>("created_at");
  const [sortDirection, setSortDirection] = useState<SortDirection>("desc");

  // Extract all unique tags from beliefs
  const allTags = useMemo(() => {
    const tags = new Set<string>();
    beliefs.forEach((belief) => {
      belief.tags?.forEach((tag) => tags.add(tag));
    });
    return Array.from(tags).sort();
  }, [beliefs]);

  // Filter and sort beliefs
  const filteredBeliefs = useMemo(() => {
    let result = beliefs.filter((belief) => {
      // Search filter
      if (searchTerm) {
        const searchLower = searchTerm.toLowerCase();
        const matchesTitle = belief.title.toLowerCase().includes(searchLower);
        const matchesSummary = belief.summary.toLowerCase().includes(searchLower);
        if (!matchesTitle && !matchesSummary) return false;
      }

      // Tags filter
      if (selectedTags.length > 0) {
        const beliefTags = belief.tags || [];
        const hasMatchingTag = selectedTags.some((tag) => beliefTags.includes(tag));
        if (!hasMatchingTag) return false;
      }

      // Confidence range filter
      const confidence = belief.confidence ?? 0.5;
      if (confidence < confidenceRange[0] || confidence > confidenceRange[1]) {
        return false;
      }

      return true;
    });

    // Sort
    result.sort((a, b) => {
      let comparison = 0;

      switch (sortBy) {
        case "title":
          comparison = a.title.localeCompare(b.title);
          break;
        case "confidence":
          comparison = (a.confidence ?? 0.5) - (b.confidence ?? 0.5);
          break;
        case "created_at":
          const dateA = a.created_at ? new Date(a.created_at).getTime() : 0;
          const dateB = b.created_at ? new Date(b.created_at).getTime() : 0;
          comparison = dateA - dateB;
          break;
      }

      return sortDirection === "asc" ? comparison : -comparison;
    });

    return result;
  }, [beliefs, searchTerm, selectedTags, confidenceRange, sortBy, sortDirection]);

  // Handle column header click for sorting
  const handleSort = (field: SortField) => {
    if (sortBy === field) {
      setSortDirection((prev) => (prev === "asc" ? "desc" : "asc"));
    } else {
      setSortBy(field);
      setSortDirection("asc");
    }
  };

  // Toggle tag selection
  const toggleTag = (tag: string) => {
    setSelectedTags((prev) =>
      prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag]
    );
  };

  // Format date for display
  const formatDate = (dateString: string | null) => {
    if (!dateString) return "Unknown";
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

    if (diffDays === 0) return "Today";
    if (diffDays === 1) return "Yesterday";
    if (diffDays < 7) return `${diffDays} days ago`;
    if (diffDays < 30) return `${Math.floor(diffDays / 7)} weeks ago`;

    return new Intl.DateTimeFormat("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    }).format(date);
  };

  // Get sort indicator
  const getSortIndicator = (field: SortField) => {
    if (sortBy !== field) return null;
    return sortDirection === "asc" ? " ^" : " v";
  };

  // Clear all filters
  const clearFilters = () => {
    setSearchTerm("");
    setSelectedTags([]);
    setConfidenceRange([0, 1]);
  };

  const hasActiveFilters =
    searchTerm !== "" ||
    selectedTags.length > 0 ||
    confidenceRange[0] > 0 ||
    confidenceRange[1] < 1;

  return (
    <div className="space-y-4">
      {/* Search and Filters */}
      <div className="card p-4 space-y-4">
        {/* Search Input */}
        <div>
          <input
            type="text"
            placeholder="Search beliefs by title or summary..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full px-4 py-2 border border-[var(--border)] rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--primary)] focus:border-transparent"
          />
        </div>

        {/* Filters Row */}
        <div className="flex flex-wrap gap-4 items-start">
          {/* Tags Filter */}
          {allTags.length > 0 && (
            <div className="flex-1 min-w-[200px]">
              <label className="block text-xs font-semibold text-[var(--text-secondary)] mb-2">
                Filter by tags
              </label>
              <div className="flex flex-wrap gap-2">
                {allTags.map((tag) => (
                  <button
                    key={tag}
                    onClick={() => toggleTag(tag)}
                    className={`chip text-xs cursor-pointer transition-colors ${
                      selectedTags.includes(tag)
                        ? "bg-[var(--primary)] text-white border-[var(--primary)]"
                        : "hover:bg-[var(--card)]"
                    }`}
                  >
                    {tag}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Confidence Range Filter */}
          <div className="min-w-[200px]">
            <label className="block text-xs font-semibold text-[var(--text-secondary)] mb-2">
              Confidence range: {Math.round(confidenceRange[0] * 100)}% - {Math.round(confidenceRange[1] * 100)}%
            </label>
            <div className="flex items-center gap-2">
              <input
                type="range"
                min="0"
                max="1"
                step="0.05"
                value={confidenceRange[0]}
                onChange={(e) =>
                  setConfidenceRange([
                    Math.min(parseFloat(e.target.value), confidenceRange[1] - 0.05),
                    confidenceRange[1],
                  ])
                }
                className="flex-1"
              />
              <input
                type="range"
                min="0"
                max="1"
                step="0.05"
                value={confidenceRange[1]}
                onChange={(e) =>
                  setConfidenceRange([
                    confidenceRange[0],
                    Math.max(parseFloat(e.target.value), confidenceRange[0] + 0.05),
                  ])
                }
                className="flex-1"
              />
            </div>
          </div>

          {/* Clear Filters */}
          {hasActiveFilters && (
            <div className="flex items-end">
              <button
                onClick={clearFilters}
                className="px-3 py-1 text-sm font-semibold text-[var(--text-secondary)] hover:text-[var(--primary)] transition-colors"
              >
                Clear filters
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Results Count */}
      <div className="text-sm text-[var(--text-secondary)]">
        Showing {filteredBeliefs.length} of {beliefs.length} beliefs
      </div>

      {/* Table */}
      <div className="card overflow-hidden">
        {filteredBeliefs.length === 0 ? (
          <div className="p-8 text-center">
            <p className="muted">
              {beliefs.length === 0
                ? "No beliefs found. Create your first belief to get started."
                : "No beliefs match your filters. Try adjusting your search criteria."}
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-[var(--border)] bg-[var(--card)]">
                  <th
                    onClick={() => handleSort("title")}
                    className="px-4 py-3 text-left text-xs font-semibold text-[var(--text-secondary)] uppercase tracking-wider cursor-pointer hover:text-[var(--primary)] select-none"
                  >
                    Title{getSortIndicator("title")}
                  </th>
                  <th
                    onClick={() => handleSort("confidence")}
                    className="px-4 py-3 text-left text-xs font-semibold text-[var(--text-secondary)] uppercase tracking-wider cursor-pointer hover:text-[var(--primary)] select-none w-40"
                  >
                    Confidence{getSortIndicator("confidence")}
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-[var(--text-secondary)] uppercase tracking-wider">
                    Tags
                  </th>
                  <th
                    onClick={() => handleSort("created_at")}
                    className="px-4 py-3 text-left text-xs font-semibold text-[var(--text-secondary)] uppercase tracking-wider cursor-pointer hover:text-[var(--primary)] select-none w-32"
                  >
                    Created{getSortIndicator("created_at")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {filteredBeliefs.map((belief, index) => {
                  const confidence = belief.confidence ?? 0.5;
                  const confidencePercent = Math.round(confidence * 100);
                  // Color based on confidence: red (low) -> yellow (mid) -> green (high)
                  const hue = confidence * 120;

                  return (
                    <tr
                      key={belief.id}
                      onClick={() => onBeliefClick(belief)}
                      className={`
                        border-b border-[var(--border)] cursor-pointer transition-colors
                        hover:bg-[var(--card)]
                        ${index % 2 === 0 ? "bg-white" : "bg-[var(--card)]/30"}
                      `}
                    >
                      <td className="px-4 py-3">
                        <div>
                          <p className="font-semibold text-[var(--primary)]">
                            {belief.title}
                          </p>
                          <p className="text-sm text-[var(--text-secondary)] truncate max-w-md">
                            {belief.summary}
                          </p>
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <div className="flex-1 h-2 bg-[var(--card)] rounded-full overflow-hidden max-w-24">
                            <div
                              className="h-full rounded-full"
                              style={{
                                width: `${confidencePercent}%`,
                                backgroundColor: `hsl(${hue}, 70%, 50%)`,
                              }}
                            />
                          </div>
                          <span className="text-sm font-semibold text-[var(--text-secondary)] w-10">
                            {confidencePercent}%
                          </span>
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex flex-wrap gap-1">
                          {belief.tags?.slice(0, 3).map((tag) => (
                            <span key={tag} className="chip text-xs">
                              {tag}
                            </span>
                          ))}
                          {(belief.tags?.length ?? 0) > 3 && (
                            <span className="text-xs text-[var(--text-secondary)]">
                              +{(belief.tags?.length ?? 0) - 3}
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="px-4 py-3 text-sm text-[var(--text-secondary)]">
                        {formatDate(belief.created_at)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
