/**
 * API Client for Reddit AI Agent Backend
 *
 * Type-safe client for interacting with FastAPI backend.
 * Types mirror Pydantic schemas from backend/app/schemas/*.py
 */

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// Type definitions matching backend schemas

export interface ActivityItem {
  id: string;
  content: string;
  interaction_type: string;
  reddit_id: string;
  subreddit: string;
  parent_id: string | null;
  created_at: string | null;
  metadata: Record<string, unknown>;
}

export interface StatsResponse {
  interactions: number;
  pending_posts: number;
  belief_updates: number;
}

export interface BeliefUpdateProposal {
  belief_id: string;
  belief_title: string;
  current_confidence: number;
  proposed_confidence: number;
  reason: string;
  evidence_strength: "weak" | "moderate" | "strong";
}

export interface NewBeliefProposal {
  title: string;
  summary: string;
  initial_confidence: number;
  tags: string[];
  reason: string;
}

export interface BeliefProposals {
  updates: BeliefUpdateProposal[];
  new_belief: NewBeliefProposal | null;
}

export interface PendingItem {
  id: string;
  persona_id: string;
  content: string;
  post_type: string | null;
  target_subreddit: string | null;
  parent_id: string | null;
  draft_metadata: Record<string, unknown>;
  status: string;
  created_at: string | null;
  belief_proposals: BeliefProposals | null;
}

export interface BeliefNode {
  id: string;
  title: string;
  summary: string;
  confidence: number | null;
  tags: string[] | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface BeliefEdge {
  id: string;
  source_id: string;
  target_id: string;
  relation: string;
  weight: number | null;
  created_at: string | null;
}

export interface BeliefGraphResponse {
  nodes: BeliefNode[];
  edges: BeliefEdge[];
}

export interface StanceModel {
  id: string;
  text: string;
  confidence: number | null;
  status: string | null;
  rationale: string | null;
  created_at: string | null;
}

export interface EvidenceModel {
  id: string;
  source_type: string;
  source_ref: string;
  strength: string | null;
  created_at: string | null;
}

export interface BeliefUpdateModel {
  id: string;
  old_value: Record<string, unknown> | null;
  new_value: Record<string, unknown> | null;
  reason: string;
  trigger_type: string | null;
  updated_by: string | null;
  created_at: string | null;
}

export interface BeliefHistoryResponse {
  belief: Record<string, unknown>;
  stances: StanceModel[];
  evidence: EvidenceModel[];
  updates: BeliefUpdateModel[];
}

export interface PersonaSummary {
  id: string;
  reddit_username: string;
  display_name: string | null;
}

export interface PersonaConfig {
  tone?: string;
  style?: string;
  core_values?: string[];
  target_subreddits?: string[];
  /**
   * Rich backstory including life events, formative experiences,
   * career path, education background, country/region, cultural context,
   * memories backing convictions, speech quirks, habits, mannerisms,
   * and emotional tendencies. Makes the persona feel human.
   */
  personality_profile?: string;
  /**
   * Explicit behavioral rules for writing style.
   * Examples: "Never use emojis", "Use contractions naturally",
   * "Vary sentence length", "Occasionally self-correct or rephrase"
   */
  writing_rules?: string[];
  /**
   * Few-shot examples of ideal responses demonstrating
   * the persona's authentic voice and style.
   */
  voice_examples?: string[];
}

export interface PersonaCreateRequest {
  reddit_username: string;
  display_name?: string;
  config?: PersonaConfig;
}

export interface PersonaCreateResponse {
  id: string;
  reddit_username: string;
  display_name: string | null;
  config: Record<string, unknown>;
  created_at: string;
}

export interface ModerationActionRequest {
  item_id: string;
  persona_id: string;
}

export interface ModerationDecisionResponse {
  item_id: string;
  status: string;
  reviewed_by: string | null;
  reviewed_at: string | null;
}

export interface BeliefUpdateRequest {
  persona_id: string;
  confidence?: number;
  text?: string;
  rationale: string;
}

export interface BeliefNudgeRequest {
  persona_id: string;
  direction: "more_confident" | "less_confident";
  amount?: number;
}

export interface BeliefLockRequest {
  persona_id: string;
  reason?: string;
}

// New types for belief creation and relationship management
export interface BeliefCreateRequest {
  persona_id: string;
  title: string;
  summary: string;
  confidence?: number;
  tags?: string[];
  auto_link?: boolean;
}

export interface BeliefCreateResponse {
  belief_id: string;
  suggested_relationships: RelationshipSuggestion[];
}

export interface RelationshipSuggestion {
  target_belief_id: string;
  target_belief_title: string;
  relation: string;
  weight: number;
  reasoning: string;
}

export interface RelationshipCreateRequest {
  persona_id: string;
  target_belief_id: string;
  relation: string;
  weight?: number;
}

export interface BeliefUpdateResponse {
  belief_id: string;
  old_confidence: number;
  new_confidence: number;
  status: string;
  message: string;
}

export interface SettingsUpdateRequest {
  persona_id: string;
  key: string;
  value: unknown;
}

export interface SettingsResponse {
  persona_id: string;
  config: Record<string, unknown>;
}

export interface DailyCostData {
  date: string;
  cost: number;
  interactions: number;
  tokens: number;
}

export interface ModelBreakdownData {
  model: string;
  cost: number;
  count: number;
  percentage: number;
  [key: string]: string | number;
}

export interface CostStatsResponse {
  total_cost: number;
  total_interactions: number;
  avg_cost_per_interaction: number;
  total_tokens_in: number;
  total_tokens_out: number;
  projected_monthly_cost: number;
  daily_costs: DailyCostData[];
  model_breakdown: ModelBreakdownData[];
}

class ApiClient {
  private baseUrl: string;
  private token: string | null = null;

  constructor(baseUrl: string = API_BASE_URL) {
    this.baseUrl = baseUrl;
    // Try to load token from localStorage if in browser
    if (typeof window !== "undefined") {
      this.token = localStorage.getItem("auth_token");
    }
  }

  setToken(token: string) {
    this.token = token;
    if (typeof window !== "undefined") {
      localStorage.setItem("auth_token", token);
      // Also set as cookie for middleware access
      document.cookie = `auth_token=${token}; path=/; max-age=86400`;
    }
  }

  clearToken() {
    this.token = null;
    if (typeof window !== "undefined") {
      localStorage.removeItem("auth_token");
      // Clear cookie
      document.cookie = "auth_token=; path=/; max-age=0";
    }
  }

  private async request<T>(
    endpoint: string,
    options?: RequestInit
  ): Promise<T> {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      ...((options?.headers as Record<string, string>) || {}),
    };

    if (this.token) {
      headers["Authorization"] = `Bearer ${this.token}`;
    }

    const response = await fetch(`${this.baseUrl}${endpoint}`, {
      ...options,
      headers,
    });

    if (!response.ok) {
      const error = await response.text();
      throw new Error(`API Error (${response.status}): ${error}`);
    }

    return response.json();
  }

  // Auth endpoints
  async login(username: string, password: string): Promise<{ access_token: string; token_type: string }> {
    const formData = new URLSearchParams();
    formData.append("username", username);
    formData.append("password", password);

    const response = await fetch(`${this.baseUrl}/api/v1/auth/token`, {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: formData,
    });

    if (!response.ok) {
      throw new Error("Login failed");
    }

    const data = await response.json();
    this.setToken(data.access_token);
    return data;
  }

  // Activity endpoints
  async getActivity(
    persona_id: string,
    options?: {
      since?: string;
      limit?: number;
      subreddit?: string;
    }
  ): Promise<ActivityItem[]> {
    const params = new URLSearchParams({ persona_id });
    if (options?.since) params.append("since", options.since);
    if (options?.limit) params.append("limit", options.limit.toString());
    if (options?.subreddit) params.append("subreddit", options.subreddit);
    return this.request(`/api/v1/activity?${params}`);
  }

  // Stats endpoints
  async getStats(persona_id: string): Promise<StatsResponse> {
    return this.request(`/api/v1/stats?persona_id=${persona_id}`);
  }

  // Belief endpoints
  async getBeliefGraph(persona_id: string): Promise<BeliefGraphResponse> {
    return this.request(`/api/v1/beliefs?persona_id=${persona_id}`);
  }

  async getBeliefHistory(belief_id: string, persona_id: string): Promise<BeliefHistoryResponse> {
    return this.request(`/api/v1/beliefs/${belief_id}/history?persona_id=${persona_id}`);
  }

  async updateBelief(belief_id: string, data: BeliefUpdateRequest): Promise<BeliefUpdateResponse> {
    return this.request(`/api/v1/beliefs/${belief_id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    });
  }

  async lockBelief(belief_id: string, data: BeliefLockRequest): Promise<void> {
    return this.request(`/api/v1/beliefs/${belief_id}/lock`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  async unlockBelief(belief_id: string, data: BeliefLockRequest): Promise<void> {
    return this.request(`/api/v1/beliefs/${belief_id}/unlock`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  async nudgeBelief(belief_id: string, data: BeliefNudgeRequest): Promise<BeliefUpdateResponse> {
    return this.request(`/api/v1/beliefs/${belief_id}/nudge`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  // Belief creation and relationship management endpoints
  async createBelief(data: BeliefCreateRequest): Promise<BeliefCreateResponse> {
    return this.request("/api/v1/beliefs", {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  async suggestRelationships(
    belief_id: string,
    persona_id: string
  ): Promise<RelationshipSuggestion[]> {
    return this.request(
      `/api/v1/beliefs/${belief_id}/suggest-relationships?persona_id=${persona_id}`,
      { method: "GET" }
    );
  }

  async createRelationship(
    belief_id: string,
    data: RelationshipCreateRequest
  ): Promise<{ edge_id: string }> {
    return this.request(`/api/v1/beliefs/${belief_id}/relationships`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  async deleteRelationship(belief_id: string, edge_id: string): Promise<void> {
    return this.request(`/api/v1/beliefs/${belief_id}/relationships/${edge_id}`, {
      method: "DELETE",
    });
  }

  // Moderation endpoints
  async getPendingPosts(persona_id: string): Promise<PendingItem[]> {
    return this.request(`/api/v1/moderation/pending?persona_id=${persona_id}`);
  }

  async approvePost(data: ModerationActionRequest): Promise<ModerationDecisionResponse> {
    return this.request("/api/v1/moderation/approve", {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  async rejectPost(data: ModerationActionRequest): Promise<ModerationDecisionResponse> {
    return this.request("/api/v1/moderation/reject", {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  // Persona endpoints
  async getPersonas(): Promise<PersonaSummary[]> {
    return this.request("/api/v1/personas");
  }

  async createPersona(data: PersonaCreateRequest): Promise<PersonaCreateResponse> {
    return this.request("/api/v1/personas", {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  // Settings endpoints
  async getSettings(persona_id: string): Promise<SettingsResponse> {
    return this.request(`/api/v1/settings?persona_id=${persona_id}`);
  }

  async updateSetting(data: SettingsUpdateRequest): Promise<void> {
    return this.request("/api/v1/settings", {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  // Cost endpoints
  async getCostStats(
    persona_id: string,
    period: "7d" | "30d" | "90d" | "all" = "30d"
  ): Promise<CostStatsResponse> {
    const params = new URLSearchParams({ persona_id, period });
    return this.request(`/api/v1/costs/stats?${params}`);
  }

  exportCosts(persona_id: string, period: "7d" | "30d" | "90d" | "all" = "30d"): string {
    const params = new URLSearchParams({ persona_id, period });
    return `${this.baseUrl}/api/v1/costs/export?${params}`;
  }

  // Agent control endpoints
  async startAgent(
    persona_id: string,
    options?: {
      interval_seconds?: number;
      max_posts_per_cycle?: number;
      response_probability?: number;
      engagement_config?: {
        score_weight?: number;
        comment_weight?: number;
        min_probability?: number;
        max_probability?: number;
        probability_midpoint?: number;
      };
    }
  ): Promise<{ persona_id: string; status: string; message: string; started_at?: string }> {
    return this.request("/api/v1/agent/start", {
      method: "POST",
      body: JSON.stringify({
        persona_id,
        // Don't send interval_seconds if not specified - let backend use default (14400 = 4 hours)
        ...(options?.interval_seconds && { interval_seconds: options.interval_seconds }),
        max_posts_per_cycle: options?.max_posts_per_cycle ?? 5,
        response_probability: options?.response_probability ?? 0.3,
        ...(options?.engagement_config && { engagement_config: options.engagement_config }),
      }),
    });
  }

  async stopAgent(persona_id: string): Promise<{ persona_id: string; status: string; message: string }> {
    return this.request("/api/v1/agent/stop", {
      method: "POST",
      body: JSON.stringify({ persona_id }),
    });
  }

  async getAgentStatus(persona_id: string): Promise<{
    persona_id: string;
    status: string;
    started_at: string | null;
    last_activity: string | null;
    error_message: string | null;
    cycle_count: number;
  }> {
    const params = new URLSearchParams({ persona_id });
    return this.request(`/api/v1/agent/status?${params}`);
  }
}

export const apiClient = new ApiClient();
