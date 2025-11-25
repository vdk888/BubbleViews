"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { apiClient, PersonaConfig } from "@/lib/api-client";
import { usePersona } from "@/hooks/usePersona";

export default function CreatePersonaPage() {
  const router = useRouter();
  const { selectPersona } = usePersona();

  // Form state
  const [redditUsername, setRedditUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [tone, setTone] = useState("casual");
  const [style, setStyle] = useState("concise");
  const [coreValues, setCoreValues] = useState("");
  const [targetSubreddits, setTargetSubreddits] = useState("");
  const [personalityProfile, setPersonalityProfile] = useState("");
  const [writingRules, setWritingRules] = useState("");
  const [voiceExamples, setVoiceExamples] = useState("");

  // UI state
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [validationErrors, setValidationErrors] = useState<Record<string, string>>({});

  const validateForm = (): boolean => {
    const errors: Record<string, string> = {};

    // Validate reddit_username
    if (!redditUsername) {
      errors.reddit_username = "Reddit username is required";
    } else if (redditUsername.length < 3) {
      errors.reddit_username = "Username must be at least 3 characters";
    } else if (!/^[a-zA-Z0-9_-]+$/.test(redditUsername)) {
      errors.reddit_username = "Username can only contain letters, numbers, underscores, and hyphens";
    } else if (redditUsername.includes(' ')) {
      errors.reddit_username = "Username cannot contain spaces";
    }

    // Validate core_values format (comma-separated)
    if (coreValues && coreValues.includes(',')) {
      const values = coreValues.split(',').map(v => v.trim()).filter(v => v);
      if (values.length === 0) {
        errors.core_values = "Enter at least one value if using commas";
      }
    }

    // Validate target_subreddits format (comma-separated)
    if (targetSubreddits && targetSubreddits.includes(',')) {
      const subreddits = targetSubreddits.split(',').map(s => s.trim()).filter(s => s);
      if (subreddits.length === 0) {
        errors.target_subreddits = "Enter at least one subreddit if using commas";
      }
    }

    setValidationErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!validateForm()) {
      return;
    }

    setLoading(true);
    setError(null);

    try {
      // Build config object
      const config: PersonaConfig = {
        tone: tone || undefined,
        style: style || undefined,
        core_values: coreValues
          ? coreValues.split(',').map(v => v.trim()).filter(v => v)
          : undefined,
        target_subreddits: targetSubreddits
          ? targetSubreddits.split(',').map(s => s.trim()).filter(s => s)
          : undefined,
        personality_profile: personalityProfile.trim() || undefined,
        writing_rules: writingRules
          ? writingRules.split('\n').map(r => r.trim()).filter(r => r)
          : undefined,
        voice_examples: voiceExamples
          ? voiceExamples.split('\n---\n').map(e => e.trim()).filter(e => e)
          : undefined,
      };

      // Create persona
      const response = await apiClient.createPersona({
        reddit_username: redditUsername,
        display_name: displayName || undefined,
        config: Object.keys(config).length > 0 ? config : undefined,
      });

      // Auto-select the new persona
      selectPersona({
        id: response.id,
        reddit_username: response.reddit_username,
        display_name: response.display_name,
      });

      // Redirect to dashboard
      router.push('/');
    } catch (err) {
      if (err instanceof Error) {
        // Parse API error message
        const message = err.message;
        if (message.includes('409')) {
          setError(`Username "${redditUsername}" already exists. Please choose a different username.`);
        } else if (message.includes('422')) {
          setError('Validation error. Please check your input and try again.');
        } else if (message.includes('401')) {
          setError('You must be logged in to create a persona.');
        } else {
          setError(`Failed to create persona: ${message}`);
        }
      } else {
        setError('An unexpected error occurred. Please try again.');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="page-shell">
      <div className="mb-6">
        <h1>Create New Persona</h1>
        <p className="muted max-w-2xl">
          Create a new Reddit AI agent persona with custom configuration and behavior.
        </p>
      </div>

      {error && (
        <div className="border border-red-200 bg-red-50 rounded-lg p-4 mb-6">
          <p className="text-red-800">{error}</p>
        </div>
      )}

      <div className="card border-[var(--border)] max-w-3xl">
        <div className="px-6 py-4 border-b border-[var(--border)]">
          <h2 className="text-lg font-semibold">Persona Details</h2>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-6">
          {/* Reddit Username */}
          <div>
            <label htmlFor="reddit_username" className="block text-sm font-semibold text-[var(--primary)] mb-2">
              Reddit Username *
            </label>
            <input
              type="text"
              id="reddit_username"
              value={redditUsername}
              onChange={(e) => setRedditUsername(e.target.value)}
              className={`w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--primary)] ${
                validationErrors.reddit_username ? 'border-red-500' : 'border-[var(--border)]'
              }`}
              placeholder="AgentBot123"
              required
              disabled={loading}
            />
            {validationErrors.reddit_username && (
              <p className="text-sm text-red-600 mt-1">{validationErrors.reddit_username}</p>
            )}
            <p className="text-xs text-[var(--text-secondary)] mt-1">
              3-255 characters. Letters, numbers, underscores, and hyphens only. No spaces.
            </p>
          </div>

          {/* Display Name */}
          <div>
            <label htmlFor="display_name" className="block text-sm font-semibold text-[var(--primary)] mb-2">
              Display Name
            </label>
            <input
              type="text"
              id="display_name"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              className="w-full px-3 py-2 border border-[var(--border)] rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--primary)]"
              placeholder="Friendly Agent"
              disabled={loading}
            />
            <p className="text-xs text-[var(--text-secondary)] mt-1">
              Human-readable name for the dashboard (optional).
            </p>
          </div>

          {/* Configuration Section */}
          <div className="border-t border-[var(--border)] pt-6">
            <h3 className="text-sm font-semibold text-[var(--primary)] mb-4">Configuration</h3>

            {/* Tone */}
            <div className="mb-4">
              <label htmlFor="tone" className="block text-sm font-semibold text-[var(--primary)] mb-2">
                Tone
              </label>
              <select
                id="tone"
                value={tone}
                onChange={(e) => setTone(e.target.value)}
                className="w-full px-3 py-2 border border-[var(--border)] rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--primary)]"
                disabled={loading}
              >
                <option value="casual">Casual</option>
                <option value="friendly">Friendly</option>
                <option value="formal">Formal</option>
                <option value="analytical">Analytical</option>
                <option value="witty">Witty</option>
              </select>
            </div>

            {/* Style */}
            <div className="mb-4">
              <label htmlFor="style" className="block text-sm font-semibold text-[var(--primary)] mb-2">
                Style
              </label>
              <select
                id="style"
                value={style}
                onChange={(e) => setStyle(e.target.value)}
                className="w-full px-3 py-2 border border-[var(--border)] rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--primary)]"
                disabled={loading}
              >
                <option value="concise">Concise</option>
                <option value="detailed">Detailed</option>
                <option value="technical">Technical</option>
              </select>
            </div>

            {/* Core Values */}
            <div className="mb-4">
              <label htmlFor="core_values" className="block text-sm font-semibold text-[var(--primary)] mb-2">
                Core Values
              </label>
              <input
                type="text"
                id="core_values"
                value={coreValues}
                onChange={(e) => setCoreValues(e.target.value)}
                className={`w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--primary)] ${
                  validationErrors.core_values ? 'border-red-500' : 'border-[var(--border)]'
                }`}
                placeholder="honesty, evidence-based reasoning, transparency"
                disabled={loading}
              />
              {validationErrors.core_values && (
                <p className="text-sm text-red-600 mt-1">{validationErrors.core_values}</p>
              )}
              <p className="text-xs text-[var(--text-secondary)] mt-1">
                Comma-separated list of values that guide the persona's behavior.
              </p>
            </div>

            {/* Target Subreddits */}
            <div>
              <label htmlFor="target_subreddits" className="block text-sm font-semibold text-[var(--primary)] mb-2">
                Target Subreddits
              </label>
              <input
                type="text"
                id="target_subreddits"
                value={targetSubreddits}
                onChange={(e) => setTargetSubreddits(e.target.value)}
                className={`w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--primary)] ${
                  validationErrors.target_subreddits ? 'border-red-500' : 'border-[var(--border)]'
                }`}
                placeholder="test, bottest, technology"
                disabled={loading}
              />
              {validationErrors.target_subreddits && (
                <p className="text-sm text-red-600 mt-1">{validationErrors.target_subreddits}</p>
              )}
              <p className="text-xs text-[var(--text-secondary)] mt-1">
                Comma-separated list of subreddit names to monitor (without r/).
              </p>
            </div>
          </div>

          {/* Rich Personality Section */}
          <div className="border-t border-[var(--border)] pt-6">
            <h3 className="text-sm font-semibold text-[var(--primary)] mb-2">Rich Personality (Optional)</h3>
            <p className="text-xs text-[var(--text-secondary)] mb-4">
              Define a detailed personality to make your agent feel like a real human, not a robot.
              Based on 2025 prompt engineering research for human-like AI personas.
            </p>

            {/* Personality Profile */}
            <div className="mb-4">
              <label htmlFor="personality_profile" className="block text-sm font-semibold text-[var(--primary)] mb-2">
                Personality Profile
              </label>
              <textarea
                id="personality_profile"
                value={personalityProfile}
                onChange={(e) => setPersonalityProfile(e.target.value)}
                className="w-full px-3 py-2 border border-[var(--border)] rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--primary)] min-h-[150px]"
                placeholder={`Leo is a 34-year-old barista from Portland, Oregon who spent five years teaching English in Japan after college. He studied philosophy at Reed College and still reads Stoic texts for fun.

His time abroad taught him to question his assumptions and appreciate different perspectives. He tends to pause mid-thought and rephrase things when he realizes he could say it better.

Gets genuinely excited about obscure coffee facts and etymology. Has a habit of making dad jokes that he thinks are funnier than they actually are. Grew up in a small town and still roots for the underdog.`}
                disabled={loading}
              />
              <p className="text-xs text-[var(--text-secondary)] mt-1">
                Rich backstory including life events, formative experiences, career path, education,
                cultural context, speech quirks, habits, mannerisms, and emotional tendencies.
              </p>
            </div>

            {/* Writing Rules */}
            <div className="mb-4">
              <label htmlFor="writing_rules" className="block text-sm font-semibold text-[var(--primary)] mb-2">
                Writing Rules
              </label>
              <textarea
                id="writing_rules"
                value={writingRules}
                onChange={(e) => setWritingRules(e.target.value)}
                className="w-full px-3 py-2 border border-[var(--border)] rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--primary)] min-h-[120px]"
                placeholder={`Never use emojis
Use contractions naturally like "I'm", "don't", "we're"
Vary sentence length - mix short punchy sentences with longer ones
Occasionally self-correct mid-response with phrases like "actually, let me rephrase that"
Show genuine curiosity by asking follow-up questions
Avoid corporate-speak and overly formal language
Reference personal experiences when relevant`}
                disabled={loading}
              />
              <p className="text-xs text-[var(--text-secondary)] mt-1">
                One rule per line. These explicit behavioral rules define how the agent writes.
              </p>
            </div>

            {/* Voice Examples */}
            <div>
              <label htmlFor="voice_examples" className="block text-sm font-semibold text-[var(--primary)] mb-2">
                Voice Examples (Optional)
              </label>
              <textarea
                id="voice_examples"
                value={voiceExamples}
                onChange={(e) => setVoiceExamples(e.target.value)}
                className="w-full px-3 py-2 border border-[var(--border)] rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--primary)] min-h-[150px]"
                placeholder={`Hm, that's a really interesting take. I used to think the same way, actually, but then I spent some time living abroad and... well, it complicated things for me. Not saying you're wrong - just that there might be more layers to it.
---
Wait, hold on - I think I misunderstood your point. Are you saying X or Y? Because those are pretty different and I want to make sure I'm responding to what you actually meant.
---
Oh man, this reminds me of something I read about last week. Let me see if I can dig up the source...`}
                disabled={loading}
              />
              <p className="text-xs text-[var(--text-secondary)] mt-1">
                Few-shot examples of ideal responses. Separate multiple examples with "---" on its own line.
                These demonstrate your agent's authentic voice and style.
              </p>
            </div>
          </div>

          {/* Submit Buttons */}
          <div className="flex gap-3 pt-4 border-t border-[var(--border)]">
            <button
              type="submit"
              disabled={loading}
              className="px-6 py-2 bg-[var(--primary)] text-white rounded-lg hover:opacity-90 transition-opacity disabled:opacity-50 disabled:cursor-not-allowed font-semibold"
            >
              {loading ? 'Creating...' : 'Create Persona'}
            </button>
            <button
              type="button"
              onClick={() => router.push('/')}
              disabled={loading}
              className="px-6 py-2 border border-[var(--border)] rounded-lg hover:bg-[var(--card)] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Cancel
            </button>
          </div>
        </form>
      </div>

      {/* Info Box */}
      <div className="border border-[var(--chart-border)] bg-[var(--chart-bg-light)] rounded-lg p-4 mt-6 max-w-3xl">
        <div className="flex items-start">
          <div className="flex-shrink-0 h-9 w-9 rounded-full border border-[var(--chart-border)] flex items-center justify-center">
            <span className="text-[var(--chart-primary)] font-bold">i</span>
          </div>
          <div className="ml-3">
            <h3 className="text-sm font-semibold text-[var(--primary)]">After Creation</h3>
            <p className="text-sm text-[var(--text-secondary)] mt-1">
              Your new persona will be immediately available in the persona selector and can be used for all operations.
              The persona will appear in the dashboard and you'll be automatically switched to it.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
