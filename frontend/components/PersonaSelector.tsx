"use client";

import { useEffect, useState } from "react";
import { apiClient, PersonaSummary } from "@/lib/api-client";
import { usePersona } from "@/hooks/usePersona";

export function PersonaSelector() {
  const [personas, setPersonas] = useState<PersonaSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const { selectedPersonaId, selectPersona } = usePersona();

  useEffect(() => {
    const token = localStorage.getItem('auth_token');
    setIsAuthenticated(!!token);
    if (token) {
      loadPersonas();
    } else {
      setLoading(false);
    }
  }, []);

  const loadPersonas = async () => {
    try {
      const data = await apiClient.getPersonas();
      setPersonas(data);

      // Auto-select first persona if none selected
      if (data.length > 0 && !selectedPersonaId) {
        selectPersona(data[0]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load personas");
    } finally {
      setLoading(false);
    }
  };

  if (!isAuthenticated) {
    return null;
  }

  if (loading) {
    return <div className="text-sm muted">Chargement...</div>;
  }

  if (error) {
    return <div className="text-sm text-red-600">Erreur : {error}</div>;
  }

  if (personas.length === 0) {
    return <div className="text-sm muted">Aucune persona trouvee</div>;
  }

  return (
    <select
      value={selectedPersonaId || ""}
      onChange={(e) => {
        const persona = personas.find((p) => p.id === e.target.value);
        if (persona) selectPersona(persona);
      }}
      className="px-3 py-2 border border-[var(--border)] rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-[var(--primary)] bg-white shadow-sm"
    >
      {personas.map((persona) => (
        <option key={persona.id} value={persona.id}>
          {persona.display_name || persona.reddit_username}
        </option>
      ))}
    </select>
  );
}
