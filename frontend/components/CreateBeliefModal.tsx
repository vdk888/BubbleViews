"use client";

import { useState, useCallback, FormEvent, ChangeEvent } from "react";
import { apiClient, BeliefCreateRequest, RelationshipSuggestion } from "@/lib/api-client";

/**
 * Form validation types
 */
interface FormErrors {
  title?: string;
  summary?: string;
  general?: string;
}

interface FormState {
  title: string;
  summary: string;
  confidence: number;
  tagsInput: string;
  tags: string[];
  autoLink: boolean;
}

/**
 * CreateBeliefModal Props
 */
interface CreateBeliefModalProps {
  isOpen: boolean;
  personaId: string;
  onClose: () => void;
  onBeliefCreated: (beliefId: string, suggestions: RelationshipSuggestion[]) => void;
}

/**
 * Validation constants
 */
const TITLE_MAX_LENGTH = 500;
const SUMMARY_MIN_LENGTH = 10;

/**
 * CreateBeliefModal Component
 *
 * A modal dialog for creating new beliefs with form validation.
 * Features:
 * - Title input with character count (max 500 chars)
 * - Summary textarea with character count (min 10 chars)
 * - Confidence slider (0-100%)
 * - Tags input with chip display
 * - Auto-link checkbox for AI relationship suggestions
 */
export function CreateBeliefModal({
  isOpen,
  personaId,
  onClose,
  onBeliefCreated,
}: CreateBeliefModalProps) {
  // Form state
  const [formState, setFormState] = useState<FormState>({
    title: "",
    summary: "",
    confidence: 50,
    tagsInput: "",
    tags: [],
    autoLink: true,
  });

  // UI state
  const [errors, setErrors] = useState<FormErrors>({});
  const [submitting, setSubmitting] = useState(false);
  const [touched, setTouched] = useState<Set<string>>(new Set());

  /**
   * Reset form to initial state
   */
  const resetForm = useCallback(() => {
    setFormState({
      title: "",
      summary: "",
      confidence: 50,
      tagsInput: "",
      tags: [],
      autoLink: true,
    });
    setErrors({});
    setTouched(new Set());
  }, []);

  /**
   * Handle modal close
   */
  const handleClose = useCallback(() => {
    if (!submitting) {
      resetForm();
      onClose();
    }
  }, [submitting, resetForm, onClose]);

  /**
   * Validate a single field
   */
  const validateField = useCallback((field: keyof FormState, value: string | number): string | undefined => {
    switch (field) {
      case "title":
        if (typeof value !== "string" || value.trim() === "") {
          return "Title is required";
        }
        if (value.length > TITLE_MAX_LENGTH) {
          return `Title must be ${TITLE_MAX_LENGTH} characters or less`;
        }
        return undefined;

      case "summary":
        if (typeof value !== "string" || value.trim() === "") {
          return "Summary is required";
        }
        if (value.length < SUMMARY_MIN_LENGTH) {
          return `Summary must be at least ${SUMMARY_MIN_LENGTH} characters`;
        }
        return undefined;

      default:
        return undefined;
    }
  }, []);

  /**
   * Validate all fields
   */
  const validateForm = useCallback((): FormErrors => {
    const newErrors: FormErrors = {};

    const titleError = validateField("title", formState.title);
    if (titleError) newErrors.title = titleError;

    const summaryError = validateField("summary", formState.summary);
    if (summaryError) newErrors.summary = summaryError;

    return newErrors;
  }, [formState.title, formState.summary, validateField]);

  /**
   * Handle input change with validation on blur
   */
  const handleInputChange = useCallback((field: keyof FormState) => (
    e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>
  ) => {
    const value = e.target.value;
    setFormState((prev) => ({ ...prev, [field]: value }));

    // Clear error when user starts typing
    if (errors[field as keyof FormErrors]) {
      setErrors((prev) => ({ ...prev, [field]: undefined }));
    }
  }, [errors]);

  /**
   * Handle field blur for validation
   */
  const handleBlur = useCallback((field: keyof FormState) => () => {
    setTouched((prev) => new Set(prev).add(field));

    const value = formState[field];
    if (typeof value === "string" || typeof value === "number") {
      const error = validateField(field, value);
      if (error) {
        setErrors((prev) => ({ ...prev, [field]: error }));
      }
    }
  }, [formState, validateField]);

  /**
   * Handle confidence slider change
   */
  const handleConfidenceChange = useCallback((e: ChangeEvent<HTMLInputElement>) => {
    setFormState((prev) => ({
      ...prev,
      confidence: parseInt(e.target.value, 10),
    }));
  }, []);

  /**
   * Handle tags input change
   */
  const handleTagsInputChange = useCallback((e: ChangeEvent<HTMLInputElement>) => {
    setFormState((prev) => ({ ...prev, tagsInput: e.target.value }));
  }, []);

  /**
   * Process tags input on blur or when comma is typed
   */
  const processTagsInput = useCallback(() => {
    const { tagsInput, tags } = formState;
    if (!tagsInput.trim()) return;

    const newTags = tagsInput
      .split(",")
      .map((tag) => tag.trim())
      .filter((tag) => tag !== "" && !tags.includes(tag));

    if (newTags.length > 0) {
      setFormState((prev) => ({
        ...prev,
        tags: [...prev.tags, ...newTags],
        tagsInput: "",
      }));
    }
  }, [formState]);

  /**
   * Handle tags input keydown for comma detection
   */
  const handleTagsKeyDown = useCallback((e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "," || e.key === "Enter") {
      e.preventDefault();
      processTagsInput();
    }
  }, [processTagsInput]);

  /**
   * Remove a tag
   */
  const removeTag = useCallback((tagToRemove: string) => {
    setFormState((prev) => ({
      ...prev,
      tags: prev.tags.filter((tag) => tag !== tagToRemove),
    }));
  }, []);

  /**
   * Handle auto-link checkbox change
   */
  const handleAutoLinkChange = useCallback((e: ChangeEvent<HTMLInputElement>) => {
    setFormState((prev) => ({ ...prev, autoLink: e.target.checked }));
  }, []);

  /**
   * Handle form submission
   */
  const handleSubmit = useCallback(async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();

    // Validate all fields
    const formErrors = validateForm();
    if (Object.keys(formErrors).length > 0) {
      setErrors(formErrors);
      // Mark all fields as touched
      setTouched(new Set(["title", "summary"]));
      return;
    }

    // Process any remaining tags in the input
    processTagsInput();

    setSubmitting(true);
    setErrors({});

    try {
      const request: BeliefCreateRequest = {
        persona_id: personaId,
        title: formState.title.trim(),
        summary: formState.summary.trim(),
        confidence: formState.confidence / 100, // Convert to 0-1 range
        tags: formState.tags.length > 0 ? formState.tags : undefined,
        auto_link: formState.autoLink,
      };

      const response = await apiClient.createBelief(request);

      // Success - call callback and close modal
      resetForm();
      onBeliefCreated(response.belief_id, response.suggested_relationships || []);
    } catch (err) {
      // Handle specific error types
      const errorMessage = err instanceof Error ? err.message : "An error occurred";

      if (errorMessage.includes("400")) {
        setErrors({ general: "Invalid form data. Please check your inputs." });
      } else if (errorMessage.includes("404")) {
        setErrors({ general: "Persona not found. Please refresh and try again." });
      } else if (errorMessage.includes("500")) {
        setErrors({ general: "Failed to create belief. Server error occurred." });
      } else if (errorMessage.toLowerCase().includes("network") || errorMessage.toLowerCase().includes("fetch")) {
        setErrors({ general: "Network error - please check your connection and try again." });
      } else {
        setErrors({ general: errorMessage });
      }
    } finally {
      setSubmitting(false);
    }
  }, [formState, personaId, validateForm, processTagsInput, resetForm, onBeliefCreated]);

  /**
   * Handle backdrop click
   */
  const handleBackdropClick = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    if (e.target === e.currentTarget) {
      handleClose();
    }
  }, [handleClose]);

  // Don't render if not open
  if (!isOpen) return null;

  const isFormValid = !errors.title && !errors.summary && formState.title.trim() !== "" && formState.summary.trim().length >= SUMMARY_MIN_LENGTH;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={handleBackdropClick}
      role="dialog"
      aria-modal="true"
      aria-labelledby="create-belief-title"
    >
      <div
        className="bg-white rounded-xl shadow-lg w-full max-w-[500px] mx-4 max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--border)]">
          <h2 id="create-belief-title" className="text-lg font-semibold text-[var(--primary)]">
            Create New Belief
          </h2>
          <button
            onClick={handleClose}
            disabled={submitting}
            className="text-[var(--text-secondary)] hover:text-[var(--primary)] transition-colors text-xl leading-none disabled:opacity-50"
            aria-label="Close modal"
          >
            x
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="px-6 py-4 space-y-5">
          {/* General Error */}
          {errors.general && (
            <div className="p-3 bg-red-50 border border-red-200 rounded-lg">
              <p className="text-sm text-red-700">{errors.general}</p>
            </div>
          )}

          {/* Title Field */}
          <div>
            <label htmlFor="belief-title" className="block text-sm font-semibold text-[var(--primary)] mb-1">
              Title <span className="text-red-500">*</span>
            </label>
            <input
              id="belief-title"
              type="text"
              value={formState.title}
              onChange={handleInputChange("title")}
              onBlur={handleBlur("title")}
              disabled={submitting}
              placeholder="Enter a concise belief title"
              className={`w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 transition-colors ${
                errors.title && touched.has("title")
                  ? "border-red-400 focus:ring-red-200"
                  : "border-[var(--border)] focus:ring-[var(--primary)]/20 focus:border-[var(--primary)]"
              } disabled:bg-gray-50 disabled:text-gray-500`}
              maxLength={TITLE_MAX_LENGTH}
              aria-invalid={errors.title && touched.has("title") ? "true" : "false"}
              aria-describedby={errors.title && touched.has("title") ? "title-error" : undefined}
            />
            <div className="flex justify-between mt-1">
              {errors.title && touched.has("title") ? (
                <p id="title-error" className="text-xs text-red-600">{errors.title}</p>
              ) : (
                <span />
              )}
              <span className="text-xs text-[var(--text-secondary)]">
                {formState.title.length}/{TITLE_MAX_LENGTH}
              </span>
            </div>
          </div>

          {/* Summary Field */}
          <div>
            <label htmlFor="belief-summary" className="block text-sm font-semibold text-[var(--primary)] mb-1">
              Summary <span className="text-red-500">*</span>
            </label>
            <textarea
              id="belief-summary"
              value={formState.summary}
              onChange={handleInputChange("summary")}
              onBlur={handleBlur("summary")}
              disabled={submitting}
              placeholder="Describe the belief in detail (minimum 10 characters)"
              rows={4}
              className={`w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 transition-colors resize-none ${
                errors.summary && touched.has("summary")
                  ? "border-red-400 focus:ring-red-200"
                  : "border-[var(--border)] focus:ring-[var(--primary)]/20 focus:border-[var(--primary)]"
              } disabled:bg-gray-50 disabled:text-gray-500`}
              aria-invalid={errors.summary && touched.has("summary") ? "true" : "false"}
              aria-describedby={errors.summary && touched.has("summary") ? "summary-error" : undefined}
            />
            <div className="flex justify-between mt-1">
              {errors.summary && touched.has("summary") ? (
                <p id="summary-error" className="text-xs text-red-600">{errors.summary}</p>
              ) : (
                <span className="text-xs text-[var(--text-secondary)]">
                  {formState.summary.length < SUMMARY_MIN_LENGTH
                    ? `${SUMMARY_MIN_LENGTH - formState.summary.length} more characters needed`
                    : ""}
                </span>
              )}
              <span className="text-xs text-[var(--text-secondary)]">
                {formState.summary.length} characters
              </span>
            </div>
          </div>

          {/* Confidence Slider */}
          <div>
            <label htmlFor="belief-confidence" className="block text-sm font-semibold text-[var(--primary)] mb-1">
              Confidence
            </label>
            <div className="flex items-center gap-3">
              <input
                id="belief-confidence"
                type="range"
                min="0"
                max="100"
                value={formState.confidence}
                onChange={handleConfidenceChange}
                disabled={submitting}
                className="flex-1"
              />
              <span className="text-sm font-semibold text-[var(--primary)] w-12 text-right">
                {formState.confidence}%
              </span>
            </div>
            <p className="text-xs text-[var(--text-secondary)] mt-1">
              How confident are you in this belief?
            </p>
          </div>

          {/* Tags Input */}
          <div>
            <label htmlFor="belief-tags" className="block text-sm font-semibold text-[var(--primary)] mb-1">
              Tags
            </label>
            <input
              id="belief-tags"
              type="text"
              value={formState.tagsInput}
              onChange={handleTagsInputChange}
              onBlur={processTagsInput}
              onKeyDown={handleTagsKeyDown}
              disabled={submitting}
              placeholder="Add tags separated by commas"
              className="w-full px-3 py-2 border border-[var(--border)] rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--primary)]/20 focus:border-[var(--primary)] disabled:bg-gray-50 disabled:text-gray-500"
            />
            {formState.tags.length > 0 && (
              <div className="flex flex-wrap gap-2 mt-2">
                {formState.tags.map((tag) => (
                  <span
                    key={tag}
                    className="inline-flex items-center gap-1 px-2 py-1 bg-gray-100 text-gray-700 text-xs font-medium rounded-full"
                  >
                    {tag}
                    <button
                      type="button"
                      onClick={() => removeTag(tag)}
                      disabled={submitting}
                      className="text-gray-500 hover:text-gray-700 ml-1 leading-none disabled:opacity-50"
                      aria-label={`Remove tag ${tag}`}
                    >
                      x
                    </button>
                  </span>
                ))}
              </div>
            )}
          </div>

          {/* Auto-link Checkbox */}
          <div className="flex items-start gap-3">
            <input
              id="belief-autolink"
              type="checkbox"
              checked={formState.autoLink}
              onChange={handleAutoLinkChange}
              disabled={submitting}
              className="mt-1 w-4 h-4 text-[var(--primary)] border-[var(--border)] rounded focus:ring-[var(--primary)]/20 disabled:opacity-50"
            />
            <div>
              <label htmlFor="belief-autolink" className="block text-sm font-semibold text-[var(--primary)]">
                Automatically suggest related beliefs
              </label>
              <p className="text-xs text-[var(--text-secondary)] mt-0.5">
                AI will suggest connections to existing beliefs
              </p>
            </div>
          </div>
        </form>

        {/* Footer */}
        <div className="flex justify-end gap-3 px-6 py-4 border-t border-[var(--border)] bg-gray-50 rounded-b-xl">
          <button
            type="button"
            onClick={handleClose}
            disabled={submitting}
            className="px-4 py-2 text-sm font-semibold text-[var(--text-secondary)] bg-white border border-[var(--border)] rounded-lg hover:bg-gray-50 transition-colors disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="submit"
            form="create-belief-form"
            onClick={(e) => {
              e.preventDefault();
              const form = document.querySelector("form");
              if (form) {
                form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
              }
            }}
            disabled={submitting || !isFormValid}
            className="px-4 py-2 text-sm font-semibold text-white bg-green-600 rounded-lg hover:bg-green-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
          >
            {submitting && (
              <svg className="animate-spin h-4 w-4 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
            )}
            {submitting ? "Creating..." : "Create"}
          </button>
        </div>
      </div>
    </div>
  );
}
