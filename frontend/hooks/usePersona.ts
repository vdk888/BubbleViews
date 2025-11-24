"use client";

import { useState, useEffect } from "react";
import { PersonaSummary } from "@/lib/api-client";

const PERSONA_STORAGE_KEY = "selected_persona_id";

export function usePersona() {
  const [selectedPersonaId, setSelectedPersonaId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    // Load from localStorage on mount - runs once
    const loadStoredPersona = () => {
      const stored = localStorage.getItem(PERSONA_STORAGE_KEY);
      setSelectedPersonaId(stored || null);
      setIsLoading(false);
    };
    loadStoredPersona();
  }, []);

  const selectPersona = (persona: PersonaSummary) => {
    setSelectedPersonaId(persona.id);
    localStorage.setItem(PERSONA_STORAGE_KEY, persona.id);
  };

  const clearPersona = () => {
    setSelectedPersonaId(null);
    localStorage.removeItem(PERSONA_STORAGE_KEY);
  };

  return {
    selectedPersonaId,
    selectPersona,
    clearPersona,
    isLoading,
  };
}
