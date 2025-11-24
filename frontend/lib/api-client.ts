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
    }
  }

  clearToken() {
    this.token = null;
    if (typeof window !== "undefined") {
      localStorage.removeItem("auth_token");
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
    return this.request(`/api/v1/belief-graph?persona_id=${persona_id}`);
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
}

export const apiClient = new ApiClient();
