"use client";

import { useEffect, useState } from "react";
import { usePersona } from "@/hooks/usePersona";
import { apiClient, SettingsResponse } from "@/lib/api-client";

interface AgentStatus {
  persona_id: string;
  status: string;
  started_at: string | null;
  last_activity: string | null;
  error_message: string | null;
  cycle_count: number;
}

export default function SettingsPage() {
  const { selectedPersonaId } = usePersona();
  const [settings, setSettings] = useState<SettingsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // Agent control state
  const [agentStatus, setAgentStatus] = useState<AgentStatus | null>(null);
  const [agentLoading, setAgentLoading] = useState(false);
  const [agentError, setAgentError] = useState<string | null>(null);
  const [runningPersonaName, setRunningPersonaName] = useState<string | null>(null);

  // Local state for editable fields
  const [targetSubreddits, setTargetSubreddits] = useState<string>("");
  const [tone, setTone] = useState<string>("casual");
  const [style, setStyle] = useState<string>("concise");
  const [coreValues, setCoreValues] = useState<string>("");
  const [personalityProfile, setPersonalityProfile] = useState<string>("");
  const [writingRules, setWritingRules] = useState<string>("");
  const [voiceExamples, setVoiceExamples] = useState<string>("");

  useEffect(() => {
    if (selectedPersonaId) {
      loadSettings();
      loadAgentStatus();
    }
  }, [selectedPersonaId]);

  // Poll agent status every 5 seconds when page is visible
  useEffect(() => {
    if (!selectedPersonaId) return;

    const interval = setInterval(() => {
      loadAgentStatus();
    }, 5000);

    return () => clearInterval(interval);
  }, [selectedPersonaId]);

  const loadSettings = async () => {
    if (!selectedPersonaId) return;

    try {
      setLoading(true);
      const data = await apiClient.getSettings(selectedPersonaId);
      setSettings(data);
      setError(null);

      // Populate local state from loaded settings
      const config = data.config;
      setTargetSubreddits(
        Array.isArray(config.target_subreddits)
          ? config.target_subreddits.join(", ")
          : ""
      );
      setTone((config.tone as string) || "casual");
      setStyle((config.style as string) || "concise");
      setCoreValues(
        Array.isArray(config.core_values)
          ? config.core_values.join(", ")
          : ""
      );
      setPersonalityProfile((config.personality_profile as string) || "");
      setWritingRules(
        Array.isArray(config.writing_rules)
          ? config.writing_rules.join("\n")
          : ""
      );
      setVoiceExamples(
        Array.isArray(config.voice_examples)
          ? config.voice_examples.join("\n---\n")
          : ""
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load settings");
    } finally {
      setLoading(false);
    }
  };

  const loadAgentStatus = async () => {
    try {
      // Use systemd status (global, not per-persona)
      const status = await apiClient.getSystemdAgentStatus();
      setAgentStatus({
        persona_id: status.persona_id || "",
        status: status.status,
        started_at: null,
        last_activity: null,
        error_message: status.status === "failed" ? status.message : null,
        cycle_count: 0,
      });
      setRunningPersonaName(status.persona_name);
      setAgentError(null);
    } catch (err) {
      setAgentError(err instanceof Error ? err.message : "Failed to load agent status");
    }
  };

  const handleStartAgent = async () => {
    if (!selectedPersonaId || agentLoading) return;

    try {
      setAgentLoading(true);
      setAgentError(null);
      const result = await apiClient.startSystemdAgent(selectedPersonaId);
      if (!result.active) {
        setAgentError(result.message);
      }
      await loadAgentStatus();
    } catch (err) {
      setAgentError(err instanceof Error ? err.message : "Failed to start agent");
    } finally {
      setAgentLoading(false);
    }
  };

  const handleStopAgent = async () => {
    if (agentLoading) return;

    try {
      setAgentLoading(true);
      setAgentError(null);
      await apiClient.stopSystemdAgent();
      await loadAgentStatus();
    } catch (err) {
      setAgentError(err instanceof Error ? err.message : "Failed to stop agent");
    } finally {
      setAgentLoading(false);
    }
  };

  const handleToggleSetting = async (key: string, currentValue: boolean) => {
    if (!selectedPersonaId || saving) return;

    try {
      setSaving(true);
      await apiClient.updateSetting({
        persona_id: selectedPersonaId,
        key,
        value: !currentValue,
      });
      await loadSettings();
    } catch (err) {
      alert(`Failed to update setting: ${err instanceof Error ? err.message : "Unknown error"}`);
    } finally {
      setSaving(false);
    }
  };

  const handleSaveTextSetting = async (key: string, value: string | string[]) => {
    if (!selectedPersonaId || saving) return;

    try {
      setSaving(true);
      await apiClient.updateSetting({
        persona_id: selectedPersonaId,
        key,
        value,
      });
      await loadSettings();
    } catch (err) {
      alert(`Failed to update setting: ${err instanceof Error ? err.message : "Unknown error"}`);
    } finally {
      setSaving(false);
    }
  };

  if (!selectedPersonaId) {
    return (
      <div className="page-shell">
        <div className="card p-4 bg-[var(--card)]">
          <p className="muted">Selectionnez une persona pour acceder aux parametres.</p>
        </div>
      </div>
    );
  }

  const autoPostingEnabled = settings?.config.auto_posting_enabled as boolean | undefined;
  const isAgentRunning = agentStatus?.status === "running";
  const hasAgentError = agentStatus?.status === "error";

  const formatTimestamp = (timestamp: string | null) => {
    if (!timestamp) return "Never";
    const date = new Date(timestamp);
    return date.toLocaleString();
  };

  return (
    <div className="page-shell">
      <div className="mb-6">
        <h1>Settings</h1>
        <p className="muted max-w-2xl">
          Ajustez le comportement de l'agent en coherence avec la promesse Bubble : transparence et controle.
        </p>
      </div>

      {error && (
        <div className="border border-red-200 bg-red-50 rounded-lg p-4 mb-6">
          <p className="text-red-800">{error}</p>
        </div>
      )}

      {loading && (
        <div className="space-y-6">
          {[1, 2, 3].map((i) => (
            <div key={i} className="card p-6 animate-pulse">
              <div className="h-4 bg-[var(--card)] rounded w-1/3 mb-2"></div>
              <div className="h-4 bg-[var(--card)] rounded w-2/3"></div>
            </div>
          ))}
        </div>
      )}

      {!loading && settings && (
        <div className="space-y-6">
          {/* Agent Control Section */}
          <div className="card border-[var(--border)]">
            <div className="px-6 py-4 border-b border-[var(--border)]">
              <h2 className="text-lg font-semibold">Agent Control</h2>
            </div>
            <div className="p-6">
              {agentError && (
                <div className="border border-red-200 bg-red-50 rounded-lg p-3 mb-4">
                  <p className="text-sm text-red-800">{agentError}</p>
                </div>
              )}

              {hasAgentError && agentStatus?.error_message && (
                <div className="border border-red-200 bg-red-50 rounded-lg p-3 mb-4">
                  <p className="text-sm font-semibold text-red-800 mb-1">Agent Error</p>
                  <p className="text-sm text-red-700">{agentStatus.error_message}</p>
                </div>
              )}

              <div className="flex items-center justify-between py-3 mb-4">
                <div className="flex items-center space-x-3">
                  <div
                    className={`w-3 h-3 rounded-full ${
                      isAgentRunning
                        ? "bg-green-500 animate-pulse"
                        : hasAgentError
                        ? "bg-red-500"
                        : "bg-gray-400"
                    }`}
                  />
                  <div>
                    <div className="flex items-center space-x-2">
                      <span className="text-sm font-semibold text-[var(--primary)]">
                        Status: {agentStatus?.status || "stopped"}
                      </span>
                      {isAgentRunning && runningPersonaName && (
                        <span className="text-xs text-[var(--text-secondary)]">
                          (running as {runningPersonaName})
                        </span>
                      )}
                    </div>
                    {isAgentRunning && runningPersonaName && agentStatus?.persona_id !== selectedPersonaId && (
                      <p className="text-xs text-amber-600 mt-0.5">
                        Warning: Agent is running a different persona
                      </p>
                    )}
                  </div>
                </div>

                <button
                  onClick={isAgentRunning ? handleStopAgent : handleStartAgent}
                  disabled={agentLoading}
                  className={`px-4 py-2 rounded-lg font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-[var(--primary)] focus:ring-offset-2 disabled:opacity-50 ${
                    isAgentRunning
                      ? "bg-red-600 text-white hover:bg-red-700"
                      : "bg-[var(--primary)] text-white hover:bg-[var(--primary-hover)]"
                  }`}
                >
                  {agentLoading ? "..." : isAgentRunning ? "Stop Agent" : "Start Agent"}
                </button>
              </div>

              {agentStatus && agentStatus.status !== "not_running" && (
                <div className="bg-[var(--card)] rounded-lg p-4 space-y-2">
                  <div className="flex justify-between text-sm">
                    <span className="text-[var(--text-secondary)]">Started At:</span>
                    <span className="font-mono text-[var(--primary)]">
                      {formatTimestamp(agentStatus.started_at)}
                    </span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-[var(--text-secondary)]">Cycle Count:</span>
                    <span className="font-mono text-[var(--primary)]">{agentStatus.cycle_count}</span>
                  </div>
                </div>
              )}

              <div className="mt-4 text-xs text-[var(--text-secondary)]">
                <p>
                  The agent loop monitors Reddit for new posts and generates responses according to your persona
                  configuration. When stopped, the agent will complete its current cycle before shutting down.
                </p>
              </div>
            </div>
          </div>

          <div className="card border-[var(--border)]">
            <div className="px-6 py-4 border-b border-[var(--border)]">
              <h2 className="text-lg font-semibold">Agent Behavior</h2>
            </div>
            <div className="p-6 space-y-4">
              <div className="flex items-center justify-between py-3">
                <div className="flex-1">
                  <h3 className="text-sm font-semibold text-[var(--primary)] mb-1">Auto-Posting</h3>
                  <p className="text-sm muted">
                    Autoriser l'agent a publier en autonomie sans relecture manuelle.
                  </p>
                </div>
                <button
                  onClick={() => handleToggleSetting("auto_posting_enabled", autoPostingEnabled || false)}
                  disabled={saving}
                  className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-[var(--primary)] focus:ring-offset-2 disabled:opacity-50 ${
                    autoPostingEnabled ? "bg-[var(--primary)]" : "bg-[var(--border)]"
                  }`}
                >
                  <span
                    className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                      autoPostingEnabled ? "translate-x-6" : "translate-x-1"
                    }`}
                  />
                </button>
              </div>
            </div>
          </div>

          <div className="card border-[var(--border)]">
            <div className="px-6 py-4 border-b border-[var(--border)]">
              <h2 className="text-lg font-semibold">Persona Configuration</h2>
            </div>
            <div className="p-6 space-y-6">
              <div>
                <label htmlFor="target-subreddits" className="block text-sm font-semibold text-[var(--primary)] mb-2">
                  Target Subreddits
                </label>
                <input
                  id="target-subreddits"
                  type="text"
                  value={targetSubreddits}
                  onChange={(e) => setTargetSubreddits(e.target.value)}
                  onBlur={() => {
                    const subreddits = targetSubreddits
                      .split(",")
                      .map((s) => s.trim())
                      .filter((s) => s.length > 0);
                    handleSaveTextSetting("target_subreddits", subreddits);
                  }}
                  placeholder="test, bottest, AskReddit"
                  disabled={saving}
                  className="w-full px-3 py-2 border border-[var(--border)] rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--primary)] disabled:opacity-50 bg-white text-[var(--text-primary)]"
                />
                <p className="text-xs text-[var(--text-secondary)] mt-1">
                  Comma-separated list of subreddits to monitor (without r/)
                </p>
              </div>

              <div>
                <label htmlFor="tone" className="block text-sm font-semibold text-[var(--primary)] mb-2">
                  Tone
                </label>
                <select
                  id="tone"
                  value={tone}
                  onChange={(e) => {
                    setTone(e.target.value);
                    handleSaveTextSetting("tone", e.target.value);
                  }}
                  disabled={saving}
                  className="w-full px-3 py-2 border border-[var(--border)] rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--primary)] disabled:opacity-50 bg-white text-[var(--text-primary)]"
                >
                  <option value="casual">Casual</option>
                  <option value="friendly">Friendly</option>
                  <option value="formal">Formal</option>
                  <option value="analytical">Analytical</option>
                  <option value="witty">Witty</option>
                </select>
                <p className="text-xs text-[var(--text-secondary)] mt-1">
                  The overall tone of voice for the agent's responses
                </p>
              </div>

              <div>
                <label htmlFor="style" className="block text-sm font-semibold text-[var(--primary)] mb-2">
                  Style
                </label>
                <select
                  id="style"
                  value={style}
                  onChange={(e) => {
                    setStyle(e.target.value);
                    handleSaveTextSetting("style", e.target.value);
                  }}
                  disabled={saving}
                  className="w-full px-3 py-2 border border-[var(--border)] rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--primary)] disabled:opacity-50 bg-white text-[var(--text-primary)]"
                >
                  <option value="concise">Concise</option>
                  <option value="detailed">Detailed</option>
                  <option value="technical">Technical</option>
                </select>
                <p className="text-xs text-[var(--text-secondary)] mt-1">
                  The writing style and level of detail in responses
                </p>
              </div>

              <div>
                <label htmlFor="core-values" className="block text-sm font-semibold text-[var(--primary)] mb-2">
                  Core Values
                </label>
                <input
                  id="core-values"
                  type="text"
                  value={coreValues}
                  onChange={(e) => setCoreValues(e.target.value)}
                  onBlur={() => {
                    const values = coreValues
                      .split(",")
                      .map((v) => v.trim())
                      .filter((v) => v.length > 0);
                    handleSaveTextSetting("core_values", values);
                  }}
                  placeholder="honesty, transparency, evidence-based reasoning"
                  disabled={saving}
                  className="w-full px-3 py-2 border border-[var(--border)] rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--primary)] disabled:opacity-50 bg-white text-[var(--text-primary)]"
                />
                <p className="text-xs text-[var(--text-secondary)] mt-1">
                  Comma-separated list of core values that guide the persona
                </p>
              </div>
            </div>
          </div>

          {/* Rich Personality Section */}
          <div className="card border-[var(--border)]">
            <div className="px-6 py-4 border-b border-[var(--border)]">
              <h2 className="text-lg font-semibold">Rich Personality</h2>
              <p className="text-xs text-[var(--text-secondary)] mt-1">
                Define a detailed personality to make your agent feel like a real human.
              </p>
            </div>
            <div className="p-6 space-y-6">
              <div>
                <label htmlFor="personality-profile" className="block text-sm font-semibold text-[var(--primary)] mb-2">
                  Personality Profile
                </label>
                <textarea
                  id="personality-profile"
                  value={personalityProfile}
                  onChange={(e) => setPersonalityProfile(e.target.value)}
                  onBlur={() => {
                    handleSaveTextSetting("personality_profile", personalityProfile.trim());
                  }}
                  placeholder={`Leo is a 34-year-old barista from Portland, Oregon who spent five years teaching English in Japan after college. He studied philosophy at Reed College and still reads Stoic texts for fun.

His time abroad taught him to question his assumptions and appreciate different perspectives. He tends to pause mid-thought and rephrase things when he realizes he could say it better.

Gets genuinely excited about obscure coffee facts and etymology.`}
                  disabled={saving}
                  className="w-full px-3 py-2 border border-[var(--border)] rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--primary)] disabled:opacity-50 bg-white text-[var(--text-primary)] min-h-[150px]"
                />
                <p className="text-xs text-[var(--text-secondary)] mt-1">
                  Rich backstory including life events, formative experiences, career path, education,
                  cultural context, speech quirks, habits, mannerisms, and emotional tendencies.
                </p>
              </div>

              <div>
                <label htmlFor="writing-rules" className="block text-sm font-semibold text-[var(--primary)] mb-2">
                  Writing Rules
                </label>
                <textarea
                  id="writing-rules"
                  value={writingRules}
                  onChange={(e) => setWritingRules(e.target.value)}
                  onBlur={() => {
                    const rules = writingRules
                      .split("\n")
                      .map((r) => r.trim())
                      .filter((r) => r.length > 0);
                    handleSaveTextSetting("writing_rules", rules);
                  }}
                  placeholder={`Never use emojis
Use contractions naturally like "I'm", "don't", "we're"
Vary sentence length - mix short punchy sentences with longer ones
Occasionally self-correct mid-response
Show genuine curiosity by asking follow-up questions
Avoid corporate-speak and overly formal language`}
                  disabled={saving}
                  className="w-full px-3 py-2 border border-[var(--border)] rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--primary)] disabled:opacity-50 bg-white text-[var(--text-primary)] min-h-[120px]"
                />
                <p className="text-xs text-[var(--text-secondary)] mt-1">
                  One rule per line. These explicit behavioral rules define how the agent writes.
                </p>
              </div>

              <div>
                <label htmlFor="voice-examples" className="block text-sm font-semibold text-[var(--primary)] mb-2">
                  Voice Examples
                </label>
                <textarea
                  id="voice-examples"
                  value={voiceExamples}
                  onChange={(e) => setVoiceExamples(e.target.value)}
                  onBlur={() => {
                    const examples = voiceExamples
                      .split("\n---\n")
                      .map((e) => e.trim())
                      .filter((e) => e.length > 0);
                    handleSaveTextSetting("voice_examples", examples);
                  }}
                  placeholder={`Hm, that's a really interesting take. I used to think the same way, actually, but then I spent some time living abroad and... well, it complicated things for me.
---
Wait, hold on - I think I misunderstood your point. Are you saying X or Y? Because those are pretty different and I want to make sure I'm responding to what you actually meant.`}
                  disabled={saving}
                  className="w-full px-3 py-2 border border-[var(--border)] rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--primary)] disabled:opacity-50 bg-white text-[var(--text-primary)] min-h-[150px]"
                />
                <p className="text-xs text-[var(--text-secondary)] mt-1">
                  Few-shot examples of ideal responses. Separate multiple examples with "---" on its own line.
                </p>
              </div>
            </div>
          </div>

          <div className="card border-[var(--border)]">
            <div className="px-6 py-4 border-b border-[var(--border)]">
              <h2 className="text-lg font-semibold">Persona Information</h2>
            </div>
            <div className="p-6">
              <dl className="space-y-4">
                <div>
                  <dt className="text-sm font-semibold text-[var(--text-secondary)]">Persona ID</dt>
                  <dd className="mt-1 text-sm font-mono text-[var(--primary)] break-all">
                    {selectedPersonaId}
                  </dd>
                </div>
              </dl>
            </div>
          </div>

          <div className="card border-[var(--border)]">
            <div className="px-6 py-4 border-b border-[var(--border)]">
              <h2 className="text-lg font-semibold">Raw Configuration</h2>
            </div>
            <div className="p-6">
              <pre className="text-xs bg-[var(--card)] p-4 rounded border border-[var(--border)] overflow-x-auto">
                {JSON.stringify(settings.config, null, 2)}
              </pre>
            </div>
          </div>

          <div className="border border-[var(--chart-border)] bg-[var(--chart-bg-light)] rounded-lg p-4">
            <div className="flex items-start">
              <div className="flex-shrink-0 h-9 w-9 rounded-full border border-[var(--chart-border)] flex items-center justify-center">
                <span className="text-[var(--chart-primary)] font-bold">i</span>
              </div>
              <div className="ml-3">
                <h3 className="text-sm font-semibold text-[var(--primary)]">Configuration Tips</h3>
                <p className="text-sm text-[var(--text-secondary)] mt-1">
                  Target subreddits determine which subreddits the agent monitors. Changes to tone, style, and values
                  take effect immediately and influence how the agent responds to posts.
                </p>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
// Force redeploy 1764195342
