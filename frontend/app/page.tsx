"use client";

import { usePersona } from "@/hooks/usePersona";
import { StatsSummary } from "@/components/StatsSummary";
import Link from "next/link";

export default function Home() {
  const { selectedPersonaId, isLoading } = usePersona();

  if (isLoading) {
    return (
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="animate-pulse">
          <div className="h-8 bg-zinc-200 dark:bg-zinc-700 rounded w-1/4 mb-4"></div>
          <div className="h-4 bg-zinc-200 dark:bg-zinc-700 rounded w-1/2 mb-8"></div>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-zinc-900 dark:text-white mb-2">
          Dashboard
        </h1>
        <p className="text-zinc-600 dark:text-zinc-400">
          Monitor and manage your autonomous Reddit AI agent
        </p>
      </div>

      {/* Stats Summary */}
      <div className="mb-8">
        <h2 className="text-lg font-semibold text-zinc-900 dark:text-white mb-4">
          Overview
        </h2>
        <StatsSummary personaId={selectedPersonaId} />
      </div>

      {/* Quick Actions */}
      <div className="mb-8">
        <h2 className="text-lg font-semibold text-zinc-900 dark:text-white mb-4">
          Quick Actions
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <Link
            href="/activity"
            className="bg-white dark:bg-zinc-800 rounded-lg shadow p-6 border border-zinc-200 dark:border-zinc-700 hover:border-blue-500 dark:hover:border-blue-500 transition-colors"
          >
            <div className="text-2xl mb-2">📊</div>
            <h3 className="font-medium text-zinc-900 dark:text-white mb-1">
              View Activity
            </h3>
            <p className="text-sm text-zinc-600 dark:text-zinc-400">
              Browse recent Reddit interactions
            </p>
          </Link>

          <Link
            href="/moderation"
            className="bg-white dark:bg-zinc-800 rounded-lg shadow p-6 border border-zinc-200 dark:border-zinc-700 hover:border-blue-500 dark:hover:border-blue-500 transition-colors"
          >
            <div className="text-2xl mb-2">✅</div>
            <h3 className="font-medium text-zinc-900 dark:text-white mb-1">
              Review Queue
            </h3>
            <p className="text-sm text-zinc-600 dark:text-zinc-400">
              Approve or reject pending posts
            </p>
          </Link>

          <Link
            href="/beliefs"
            className="bg-white dark:bg-zinc-800 rounded-lg shadow p-6 border border-zinc-200 dark:border-zinc-700 hover:border-blue-500 dark:hover:border-blue-500 transition-colors"
          >
            <div className="text-2xl mb-2">🧠</div>
            <h3 className="font-medium text-zinc-900 dark:text-white mb-1">
              Belief Graph
            </h3>
            <p className="text-sm text-zinc-600 dark:text-zinc-400">
              Explore agent belief system
            </p>
          </Link>

          <Link
            href="/settings"
            className="bg-white dark:bg-zinc-800 rounded-lg shadow p-6 border border-zinc-200 dark:border-zinc-700 hover:border-blue-500 dark:hover:border-blue-500 transition-colors"
          >
            <div className="text-2xl mb-2">⚙️</div>
            <h3 className="font-medium text-zinc-900 dark:text-white mb-1">
              Settings
            </h3>
            <p className="text-sm text-zinc-600 dark:text-zinc-400">
              Configure agent behavior
            </p>
          </Link>
        </div>
      </div>

      {/* Status */}
      <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
        <div className="flex items-start">
          <div className="flex-shrink-0">
            <span className="text-2xl">ℹ️</span>
          </div>
          <div className="ml-3">
            <h3 className="text-sm font-medium text-blue-800 dark:text-blue-200">
              MVP Dashboard - Week 4
            </h3>
            <div className="mt-2 text-sm text-blue-700 dark:text-blue-300">
              <p>
                This dashboard provides monitoring and control for your autonomous Reddit AI agent.
                Features include activity tracking, belief graph visualization, and moderation queue management.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
