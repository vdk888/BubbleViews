"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiClient, PersonaSummary } from "@/lib/api-client";
import { usePersona } from "@/hooks/usePersona";

export function PersonaSelector() {
  const router = useRouter();
  const [personas, setPersonas] = useState<PersonaSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [mounted, setMounted] = useState(false);
  const { selectedPersonaId, selectPersona } = usePersona();

  useEffect(() => {
    setMounted(true);
    const token = localStorage.getItem("auth_token");
    if (token) {
      // Ensure apiClient has the token before making requests
      apiClient.setToken(token);
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
      // On any error, just show empty personas state (allow creating)
      console.error("Failed to load personas:", err);
      setPersonas([]);
    } finally {
      setLoading(false);
    }
  };

  // Don't render anything until mounted (avoid hydration mismatch)
  if (!mounted) {
    return null;
  }

  // Show loading state
  if (loading) {
    return <div className="text-sm muted">Chargement...</div>;
  }

  // No personas - show create button
  if (personas.length === 0) {
    return (
      <div className="flex items-center gap-2">
        <span className="text-sm muted">Aucune persona</span>
        <button
          onClick={() => router.push("/personas/create")}
          className="px-3 py-1.5 bg-[var(--primary)] text-white text-xs font-semibold rounded-md hover:opacity-90 transition-opacity"
        >
          Creer
        </button>
      </div>
    );
  }

  // Has personas - show dropdown + add button
  return (
    <div className="flex items-center gap-2">
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
      <button
        onClick={() => router.push("/personas/create")}
        className="px-2 py-1.5 border border-[var(--border)] rounded-md text-xs font-semibold hover:bg-[var(--card)] transition-colors"
        title="Create new persona"
      >
        +
      </button>
    </div>
  );
}
