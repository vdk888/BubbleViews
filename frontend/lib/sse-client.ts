/**
 * SSE Client for real-time dashboard updates.
 *
 * Manages EventSource connections to the backend SSE endpoint,
 * handling reconnection logic and event distribution.
 */

export type SSEEventType =
  | "new_interaction"
  | "pending_post_added"
  | "belief_updated"
  | "agent_status_changed";

export interface SSEEvent {
  type: SSEEventType;
  persona_id: string;
  data: Record<string, any>;
  timestamp: string;
}

export type SSEEventHandler = (event: SSEEvent) => void;

export interface SSEClientOptions {
  /**
   * Maximum number of reconnection attempts before giving up.
   * Set to Infinity for unlimited retries.
   */
  maxRetries?: number;

  /**
   * Initial reconnection delay in milliseconds.
   * Delay increases exponentially on subsequent retries.
   */
  initialRetryDelay?: number;

  /**
   * Maximum reconnection delay in milliseconds.
   */
  maxRetryDelay?: number;

  /**
   * Custom base URL for the API.
   * Defaults to NEXT_PUBLIC_API_URL environment variable.
   */
  baseUrl?: string;
}

/**
 * SSE Client for managing EventSource connections with auto-reconnect.
 *
 * Example usage:
 * ```typescript
 * const client = new SSEClient();
 *
 * client.connect('persona-123', (event) => {
 *   console.log('Received event:', event.type, event.data);
 * });
 *
 * // Later, disconnect
 * client.disconnect();
 * ```
 */
export class SSEClient {
  private eventSource: EventSource | null = null;
  private personaId: string | null = null;
  private eventHandler: SSEEventHandler | null = null;
  private retryCount = 0;
  private retryTimeout: NodeJS.Timeout | null = null;
  private isManualDisconnect = false;
  private options: Required<SSEClientOptions>;

  constructor(options: SSEClientOptions = {}) {
    this.options = {
      maxRetries: options.maxRetries ?? Infinity,
      initialRetryDelay: options.initialRetryDelay ?? 1000,
      maxRetryDelay: options.maxRetryDelay ?? 30000,
      baseUrl:
        options.baseUrl ??
        process.env.NEXT_PUBLIC_API_URL ??
        "http://localhost:8000",
    };
  }

  /**
   * Connect to SSE stream for a specific persona.
   *
   * @param personaId - Persona ID to subscribe to
   * @param onMessage - Callback function for handling events
   */
  connect(personaId: string, onMessage: SSEEventHandler): void {
    this.personaId = personaId;
    this.eventHandler = onMessage;
    this.isManualDisconnect = false;
    this.retryCount = 0;

    this.createConnection();
  }

  /**
   * Disconnect from SSE stream.
   * Prevents automatic reconnection.
   */
  disconnect(): void {
    this.isManualDisconnect = true;
    this.cleanup();
  }

  /**
   * Check if currently connected.
   */
  isConnected(): boolean {
    return this.eventSource?.readyState === EventSource.OPEN;
  }

  /**
   * Get current connection state.
   */
  getReadyState():
    | "connecting"
    | "open"
    | "closed"
    | null {
    if (!this.eventSource) return null;

    switch (this.eventSource.readyState) {
      case EventSource.CONNECTING:
        return "connecting";
      case EventSource.OPEN:
        return "open";
      case EventSource.CLOSED:
        return "closed";
      default:
        return null;
    }
  }

  /**
   * Create EventSource connection.
   */
  private createConnection(): void {
    if (!this.personaId || !this.eventHandler) {
      console.error("[SSEClient] Cannot connect: missing personaId or eventHandler");
      return;
    }

    const url = `${this.options.baseUrl}/api/v1/stream?persona_id=${encodeURIComponent(
      this.personaId
    )}`;

    console.log(`[SSEClient] Connecting to ${url}`);

    try {
      this.eventSource = new EventSource(url);

      // Handle connection open
      this.eventSource.onopen = () => {
        console.log(`[SSEClient] Connected to persona ${this.personaId}`);
        this.retryCount = 0; // Reset retry counter on successful connection
      };

      // Handle incoming messages
      this.eventSource.onmessage = (event: MessageEvent) => {
        try {
          const data: SSEEvent = JSON.parse(event.data);
          this.eventHandler?.(data);
        } catch (error) {
          console.error("[SSEClient] Failed to parse event data:", error);
        }
      };

      // Handle specific event types
      this.setupEventListeners();

      // Handle errors and reconnection
      this.eventSource.onerror = (error) => {
        console.error("[SSEClient] Connection error:", error);

        // Close current connection
        this.eventSource?.close();

        // Attempt reconnection if not manually disconnected
        if (!this.isManualDisconnect) {
          this.scheduleReconnect();
        }
      };
    } catch (error) {
      console.error("[SSEClient] Failed to create EventSource:", error);
      if (!this.isManualDisconnect) {
        this.scheduleReconnect();
      }
    }
  }

  /**
   * Set up event listeners for specific event types.
   */
  private setupEventListeners(): void {
    if (!this.eventSource) return;

    const eventTypes: SSEEventType[] = [
      "new_interaction",
      "pending_post_added",
      "belief_updated",
      "agent_status_changed",
    ];

    eventTypes.forEach((type) => {
      this.eventSource?.addEventListener(type, (event: Event) => {
        try {
          const messageEvent = event as MessageEvent;
          const data: SSEEvent = JSON.parse(messageEvent.data);
          this.eventHandler?.(data);
        } catch (error) {
          console.error(`[SSEClient] Failed to parse ${type} event:`, error);
        }
      });
    });
  }

  /**
   * Schedule reconnection with exponential backoff.
   */
  private scheduleReconnect(): void {
    if (this.retryCount >= this.options.maxRetries) {
      console.error(
        `[SSEClient] Max retry attempts (${this.options.maxRetries}) reached. Giving up.`
      );
      return;
    }

    // Calculate exponential backoff delay
    const delay = Math.min(
      this.options.initialRetryDelay * Math.pow(2, this.retryCount),
      this.options.maxRetryDelay
    );

    this.retryCount++;

    console.log(
      `[SSEClient] Scheduling reconnect attempt ${this.retryCount} in ${delay}ms`
    );

    this.retryTimeout = setTimeout(() => {
      console.log(`[SSEClient] Attempting reconnect (${this.retryCount}/${this.options.maxRetries})`);
      this.createConnection();
    }, delay);
  }

  /**
   * Cleanup resources.
   */
  private cleanup(): void {
    if (this.retryTimeout) {
      clearTimeout(this.retryTimeout);
      this.retryTimeout = null;
    }

    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
    }

    this.personaId = null;
    this.eventHandler = null;
    this.retryCount = 0;
  }
}
