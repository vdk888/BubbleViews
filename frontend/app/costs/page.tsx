"use client";

import { useEffect, useState } from "react";
import { usePersona } from "@/hooks/usePersona";
import { apiClient, CostStatsResponse } from "@/lib/api-client";
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

export default function CostsPage() {
  const { selectedPersonaId } = usePersona();
  const [period, setPeriod] = useState<"7d" | "30d" | "90d" | "all">("30d");
  const [stats, setStats] = useState<CostStatsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (selectedPersonaId) {
      loadStats();
    }
  }, [selectedPersonaId, period]);

  const loadStats = async () => {
    if (!selectedPersonaId) return;

    try {
      setLoading(true);
      const data = await apiClient.getCostStats(selectedPersonaId, period);
      setStats(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load cost stats");
    } finally {
      setLoading(false);
    }
  };

  const exportCSV = () => {
    if (!selectedPersonaId) return;
    const url = apiClient.exportCosts(selectedPersonaId, period);
    window.open(url, "_blank");
  };

  const formatCurrency = (value: number) => {
    return `$${value.toFixed(4)}`;
  };

  const formatNumber = (value: number) => {
    return value.toLocaleString();
  };

  const COLORS = ["#0088FE", "#00C49F", "#FFBB28", "#FF8042", "#8884D8", "#82CA9D"];

  if (!selectedPersonaId) {
    return (
      <div className="page-shell">
        <div className="card p-4 bg-[var(--card)]">
          <p className="muted">Select a persona to view cost monitoring.</p>
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="page-shell">
        <div className="mb-6">
          <h1>Cost Monitoring</h1>
          <p className="muted max-w-2xl">
            Track LLM costs and token usage over time for budget management.
          </p>
        </div>
        <div className="space-y-6">
          {[1, 2, 3].map((i) => (
            <div key={i} className="card p-6 animate-pulse">
              <div className="h-4 bg-[var(--card)] rounded w-1/4 mb-2"></div>
              <div className="h-32 bg-[var(--card)] rounded"></div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="page-shell">
        <div className="mb-6">
          <h1>Cost Monitoring</h1>
        </div>
        <div className="border border-red-200 bg-red-50 rounded-lg p-4">
          <p className="text-red-800">{error}</p>
        </div>
      </div>
    );
  }

  if (!stats) return null;

  return (
    <div className="page-shell">
      <div className="mb-6">
        <h1>Cost Monitoring</h1>
        <p className="muted max-w-2xl">
          Track LLM costs and token usage over time for budget management.
        </p>
      </div>

      {/* Period selector and export */}
      <div className="mb-6 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div className="flex items-center gap-2">
          {(["7d", "30d", "90d", "all"] as const).map((p) => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                period === p
                  ? "bg-[var(--primary)] text-white"
                  : "bg-white border border-[var(--border)] text-[var(--text-primary)] hover:bg-gray-50"
              }`}
            >
              {p === "all" ? "All Time" : p.toUpperCase()}
            </button>
          ))}
        </div>
        <button
          onClick={exportCSV}
          className="pill-button text-sm bg-green-600 hover:bg-green-700 text-white"
        >
          Export CSV
        </button>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <SummaryCard
          title="Total Cost"
          value={formatCurrency(stats.total_cost)}
          subtitle={`${stats.total_interactions} interactions`}
        />
        <SummaryCard
          title="Avg per Interaction"
          value={formatCurrency(stats.avg_cost_per_interaction)}
          subtitle="Cost efficiency"
        />
        <SummaryCard
          title="Total Interactions"
          value={formatNumber(stats.total_interactions)}
          subtitle={`${formatNumber(stats.total_tokens_in + stats.total_tokens_out)} tokens`}
        />
        <SummaryCard
          title="Projected Monthly"
          value={formatCurrency(stats.projected_monthly_cost)}
          subtitle="Based on current usage"
        />
      </div>

      {/* Daily Cost Trend */}
      {stats.daily_costs.length > 0 && (
        <div className="card p-6 mb-6">
          <h2 className="text-lg font-semibold mb-4">Daily Cost Trend</h2>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={stats.daily_costs}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 12 }}
                tickFormatter={(value) => {
                  const date = new Date(value);
                  return `${date.getMonth() + 1}/${date.getDate()}`;
                }}
              />
              <YAxis tick={{ fontSize: 12 }} tickFormatter={(value) => `$${value}`} />
              <Tooltip
                formatter={(value: number) => [formatCurrency(value), "Cost"]}
                labelFormatter={(label) => `Date: ${label}`}
              />
              <Legend />
              <Line
                type="monotone"
                dataKey="cost"
                stroke="#0088FE"
                strokeWidth={2}
                dot={{ r: 3 }}
                name="Daily Cost ($)"
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Model Breakdown - Pie and Bar */}
      {stats.model_breakdown.length > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
          {/* Pie Chart */}
          <div className="card p-6">
            <h2 className="text-lg font-semibold mb-4">Cost by Model</h2>
            <ResponsiveContainer width="100%" height={300}>
              <PieChart>
                <Pie
                  data={stats.model_breakdown}
                  dataKey="cost"
                  nameKey="model"
                  cx="50%"
                  cy="50%"
                  outerRadius={100}
                  label={(entry) => `${entry.model}: ${entry.percentage}%`}
                  labelLine={{ stroke: "#666", strokeWidth: 1 }}
                >
                  {stats.model_breakdown.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip formatter={(value: number) => formatCurrency(value)} />
              </PieChart>
            </ResponsiveContainer>
          </div>

          {/* Bar Chart */}
          <div className="card p-6">
            <h2 className="text-lg font-semibold mb-4">Model Usage Count</h2>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={stats.model_breakdown}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis dataKey="model" tick={{ fontSize: 12 }} />
                <YAxis tick={{ fontSize: 12 }} />
                <Tooltip />
                <Bar dataKey="count" fill="#82ca9d" name="Interactions" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Token Usage Statistics */}
      <div className="card p-6">
        <h2 className="text-lg font-semibold mb-4">Token Usage</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div>
            <p className="text-sm text-[var(--text-secondary)] mb-1">Total Tokens In</p>
            <p className="text-2xl font-bold text-[var(--primary)]">
              {formatNumber(stats.total_tokens_in)}
            </p>
          </div>
          <div>
            <p className="text-sm text-[var(--text-secondary)] mb-1">Total Tokens Out</p>
            <p className="text-2xl font-bold text-[var(--primary)]">
              {formatNumber(stats.total_tokens_out)}
            </p>
          </div>
          <div>
            <p className="text-sm text-[var(--text-secondary)] mb-1">Total Tokens</p>
            <p className="text-2xl font-bold text-[var(--primary)]">
              {formatNumber(stats.total_tokens_in + stats.total_tokens_out)}
            </p>
          </div>
        </div>
      </div>

      {/* Model Breakdown Table */}
      {stats.model_breakdown.length > 0 && (
        <div className="card p-6 mt-6">
          <h2 className="text-lg font-semibold mb-4">Detailed Model Breakdown</h2>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-[var(--border)]">
                  <th className="text-left py-2 px-3 text-sm font-semibold text-[var(--text-secondary)]">
                    Model
                  </th>
                  <th className="text-right py-2 px-3 text-sm font-semibold text-[var(--text-secondary)]">
                    Cost
                  </th>
                  <th className="text-right py-2 px-3 text-sm font-semibold text-[var(--text-secondary)]">
                    Count
                  </th>
                  <th className="text-right py-2 px-3 text-sm font-semibold text-[var(--text-secondary)]">
                    Percentage
                  </th>
                </tr>
              </thead>
              <tbody>
                {stats.model_breakdown.map((model, idx) => (
                  <tr key={idx} className="border-b border-[var(--border)]">
                    <td className="py-2 px-3 text-sm">{model.model}</td>
                    <td className="py-2 px-3 text-sm text-right font-mono">
                      {formatCurrency(model.cost)}
                    </td>
                    <td className="py-2 px-3 text-sm text-right">{model.count}</td>
                    <td className="py-2 px-3 text-sm text-right">{model.percentage}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

function SummaryCard({
  title,
  value,
  subtitle,
}: {
  title: string;
  value: string;
  subtitle?: string;
}) {
  return (
    <div className="card p-4">
      <p className="text-sm text-[var(--text-secondary)] mb-1">{title}</p>
      <p className="text-2xl font-bold text-[var(--primary)] mb-1">{value}</p>
      {subtitle && <p className="text-xs text-[var(--text-secondary)]">{subtitle}</p>}
    </div>
  );
}
