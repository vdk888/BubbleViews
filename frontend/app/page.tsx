"use client";

import { StatsSummary } from "@/components/StatsSummary";
import { AgentControlPanel } from "@/components/AgentControlPanel";
import { usePersona } from "@/hooks/usePersona";
import { useAuth } from "@/hooks/useAuth";
import Link from "next/link";

export default function Home() {
  const { isAuthenticated, isLoading: authLoading } = useAuth();
  const { selectedPersonaId, isLoading } = usePersona();

  if (authLoading || isLoading) {
    return (
      <div className="page-shell">
        <div className="animate-pulse">
          <div className="h-8 bg-[var(--card)] rounded w-1/4 mb-4"></div>
          <div className="h-4 bg-[var(--card)] rounded w-1/2 mb-8"></div>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return null;
  }

  return (
    <div className="page-shell">
      <div className="grid grid-cols-1 lg:grid-cols-[1.2fr,0.8fr] gap-8 mb-10">
        <div className="space-y-4">
          <span className="chip">Dashboard</span>
          <h1>Bubble. Dashboard</h1>
          <p className="tagline">L'investissement optimise a l'ere de l'IA</p>
          <p className="text-lg muted max-w-2xl">
            Une interface claire, transparente et sobre pour piloter votre agent Reddit autonome,
            suivre ses interactions et controler sa gouvernance.
          </p>
          <div className="flex flex-wrap gap-3">
            <Link href="/activity" className="pill-button text-sm">
              Voir l'activite
            </Link>
            <Link href="/moderation" className="soft-button text-sm">
              File de moderation
            </Link>
          </div>
        </div>

        <AgentControlPanel personaId={selectedPersonaId} />
      </div>

      <div className="section pt-0">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-2xl font-bold">Vue synthetique</h2>
          <p className="muted text-sm">Donnees cles en direct</p>
        </div>
        <StatsSummary personaId={selectedPersonaId} />
      </div>

      <div className="section pt-4">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-2xl font-bold">Actions rapides</h2>
          <p className="muted text-sm">Controlez l'essentiel en deux clics</p>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <Link
            href="/activity"
            className="card p-5 transition duration-300 ease-out hover:-translate-y-1 hover:shadow-strong"
          >
            <div className="flex items-center justify-between mb-3">
              <span className="text-sm font-semibold text-[var(--text-secondary)]">Activity</span>
              <span className="text-lg">{"->"}</span>
            </div>
            <h4 className="mb-2">View Activity</h4>
            <p className="muted text-sm">Parcourir les interactions Reddit recentes.</p>
          </Link>

          <Link
            href="/moderation"
            className="card p-5 transition duration-300 ease-out hover:-translate-y-1 hover:shadow-strong"
          >
            <div className="flex items-center justify-between mb-3">
              <span className="text-sm font-semibold text-[var(--text-secondary)]">Review</span>
              <span className="text-lg">{"->"}</span>
            </div>
            <h4 className="mb-2">Review Queue</h4>
            <p className="muted text-sm">Approuver ou rejeter les contenus en attente.</p>
          </Link>

          <Link
            href="/beliefs"
            className="card p-5 transition duration-300 ease-out hover:-translate-y-1 hover:shadow-strong"
          >
            <div className="flex items-center justify-between mb-3">
              <span className="text-sm font-semibold text-[var(--text-secondary)]">Beliefs</span>
              <span className="text-lg">{"->"}</span>
            </div>
            <h4 className="mb-2">Belief Graph</h4>
            <p className="muted text-sm">Explorer le graphe de croyances de l'agent.</p>
          </Link>

          <Link
            href="/settings"
            className="card p-5 transition duration-300 ease-out hover:-translate-y-1 hover:shadow-strong"
          >
            <div className="flex items-center justify-between mb-3">
              <span className="text-sm font-semibold text-[var(--text-secondary)]">Governance</span>
              <span className="text-lg">{"->"}</span>
            </div>
            <h4 className="mb-2">Settings</h4>
            <p className="muted text-sm">Configurer l'agent et ses comportements.</p>
          </Link>
        </div>
      </div>
    </div>
  );
}
