/**
 * API Client for Reddit AI Agent Backend
 *
 * Type-safe client for interacting with FastAPI backend.
 * Eventually will be generated from OpenAPI spec.
 */

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface Activity {
  id: string;
  type: "comment" | "post" | "belief_update" | "moderation";
  content: string;
  timestamp: string;
  metadata?: Record<string, unknown>;
}

export interface Belief {
  id: string;
  title: string;
  summary: string;
  confidence: number;
  tags: string[];
  created_at: string;
  updated_at: string;
}

export interface PendingPost {
  id: string;
  content: string;
  post_type: string;
  target_subreddit: string;
  status: "pending" | "approved" | "rejected";
  created_at: string;
}

class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string = API_BASE_URL) {
    this.baseUrl = baseUrl;
  }

  private async request<T>(
    endpoint: string,
    options?: RequestInit
  ): Promise<T> {
    const response = await fetch(`${this.baseUrl}${endpoint}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...options?.headers,
      },
    });

    if (!response.ok) {
      throw new Error(`API Error: ${response.statusText}`);
    }

    return response.json();
  }

  // Activity endpoints
  async getActivity(since?: string, limit?: number): Promise<Activity[]> {
    const params = new URLSearchParams();
    if (since) params.append("since", since);
    if (limit) params.append("limit", limit.toString());
    return this.request(`/api/v1/activity?${params}`);
  }

  // Belief endpoints
  async getBeliefs(tags?: string[]): Promise<Belief[]> {
    const params = tags ? `?tags=${tags.join(",")}` : "";
    return this.request(`/api/v1/beliefs${params}`);
  }

  async getBelief(id: string): Promise<Belief> {
    return this.request(`/api/v1/beliefs/${id}`);
  }

  async updateBelief(id: string, data: Partial<Belief>): Promise<Belief> {
    return this.request(`/api/v1/beliefs/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    });
  }

  // Moderation endpoints
  async getPendingPosts(): Promise<PendingPost[]> {
    return this.request("/api/v1/moderation/pending");
  }

  async approvePost(id: string): Promise<void> {
    return this.request("/api/v1/moderation/approve", {
      method: "POST",
      body: JSON.stringify({ id }),
    });
  }

  async rejectPost(id: string): Promise<void> {
    return this.request("/api/v1/moderation/reject", {
      method: "POST",
      body: JSON.stringify({ id }),
    });
  }

  // Settings endpoints
  async getSettings(): Promise<Record<string, unknown>> {
    return this.request("/api/v1/settings");
  }

  async updateSettings(settings: Record<string, unknown>): Promise<void> {
    return this.request("/api/v1/settings", {
      method: "POST",
      body: JSON.stringify(settings),
    });
  }
}

export const apiClient = new ApiClient();
