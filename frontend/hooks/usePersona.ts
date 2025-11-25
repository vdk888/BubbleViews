"use client";

import { useState, useEffect, useCallback } from "react";
import { PersonaSummary } from "@/lib/api-client";

const PERSONA_STORAGE_KEY = "selected_persona_id";

export function usePersona() {
  const [selectedPersonaId, setSelectedPersonaId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // Load initial value and listen for changes
  useEffect(() => {
    // Load from localStorage on mount
    const stored = localStorage.getItem(PERSONA_STORAGE_KEY);
    setSelectedPersonaId(stored || null);
    setIsLoading(false);

    // Listen for storage changes (from other components or tabs)
    const handleStorageChange = (e: StorageEvent) => {
      if (e.key === PERSONA_STORAGE_KEY) {
        setSelectedPersonaId(e.newValue || null);
      }
    };

    // Listen for custom event for same-tab updates
    const handlePersonaChange = (e: CustomEvent<string | null>) => {
      setSelectedPersonaId(e.detail);
    };

    window.addEventListener("storage", handleStorageChange);
    window.addEventListener("persona-changed", handlePersonaChange as EventListener);

    return () => {
      window.removeEventListener("storage", handleStorageChange);
      window.removeEventListener("persona-changed", handlePersonaChange as EventListener);
    };
  }, []);

  const selectPersona = useCallback((persona: PersonaSummary) => {
    setSelectedPersonaId(persona.id);
    localStorage.setItem(PERSONA_STORAGE_KEY, persona.id);
    // Dispatch custom event for same-tab updates
    window.dispatchEvent(new CustomEvent("persona-changed", { detail: persona.id }));
  }, []);

  const clearPersona = useCallback(() => {
    setSelectedPersonaId(null);
    localStorage.removeItem(PERSONA_STORAGE_KEY);
    // Dispatch custom event for same-tab updates
    window.dispatchEvent(new CustomEvent("persona-changed", { detail: null }));
  }, []);

  return {
    selectedPersonaId,
    selectPersona,
    clearPersona,
    isLoading,
  };
}
