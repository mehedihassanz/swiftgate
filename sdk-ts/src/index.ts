// TypeScript client SDK for SwiftGate
// Generated as a single file for simplicity — no build step required.

export interface SwiftGateClientOptions {
  baseURL?: string;
  apiKey?: string;
  timeout?: number;
}

export interface Message {
  role: string;
  content: string | any[];
}

export interface PredictRequest {
  model: string;
  messages: Message[];
  max_tokens?: number;
  tools?: any[];
}

export interface QualityRouteRequest {
  messages: Message[];
  max_budget_cents?: number;
  min_quality?: number;
  top_n?: number;
}

export class SwiftGateClient {
  private baseURL: string;
  private apiKey?: string;
  private timeout: number;

  constructor(opts: SwiftGateClientOptions = {}) {
    this.baseURL = (opts.baseURL || "http://localhost:8000").replace(/\/$/, "");
    this.apiKey = opts.apiKey;
    this.timeout = opts.timeout || 120000;
  }

  private async request<T = any>(
    method: string,
    path: string,
    body?: any,
    params?: Record<string, any>,
  ): Promise<T> {
    const url = new URL(this.baseURL + path);
    if (params) {
      for (const [k, v] of Object.entries(params)) {
        if (v !== undefined && v !== null) url.searchParams.set(k, String(v));
      }
    }

    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      Accept: "application/json",
    };
    if (this.apiKey) headers["Authorization"] = `Bearer ${this.apiKey}`;

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeout);

    try {
      const resp = await fetch(url.toString(), {
        method,
        headers,
        body: body ? JSON.stringify(body) : undefined,
        signal: controller.signal,
      });

      if (!resp.ok) {
        const text = await resp.text();
        let msg = text;
        try {
          const j = JSON.parse(text);
          msg = j.detail || j.message || j.error || text;
        } catch {}
        throw new SwiftGateError(`API error ${resp.status}: ${msg}`, resp.status, resp);
      }

      if (resp.status === 204) return undefined as T;
      return (await resp.json()) as T;
    } finally {
      clearTimeout(timer);
    }
  }

  // ─── Cost Prediction ──────────────────────────────────────────────

  async predict(req: PredictRequest): Promise<any> {
    return this.request("POST", "/v1/predict", req);
  }

  async compare(
    messages: Message[],
    opts: { max_tokens?: number; max_budget_cents?: number } = {},
  ): Promise<any> {
    return this.request("POST", "/v1/compare", { messages, ...opts });
  }

  // ─── Chat (OpenAI-compatible) ─────────────────────────────────────

  async chat(
    model: string,
    messages: Message[],
    opts: {
      stream?: boolean;
      agent_id?: string;
      cost_prediction?: boolean;
      max_tokens?: number;
      temperature?: number;
      tools?: any[];
    } = {},
  ): Promise<any> {
    return this.request("POST", "/v1/chat/completions", { model, messages, ...opts });
  }

  // ─── Models ───────────────────────────────────────────────────────

  async listModels(): Promise<any> {
    return this.request("GET", "/v1/models");
  }

  async pareto(): Promise<any> {
    return this.request("GET", "/v1/pareto");
  }

  // ─── Quality ──────────────────────────────────────────────────────

  async qualityFeedback(
    modelId: string,
    rating: number,
    opts: { task_type?: string; signal_type?: string } = {},
  ): Promise<any> {
    return this.request("POST", "/v1/quality/feedback", {
      model_id: modelId,
      rating,
      ...opts,
    });
  }

  async qualityRoute(req: QualityRouteRequest): Promise<any> {
    return this.request("POST", "/v1/quality/route", req);
  }

  async qualityLeaderboard(opts: { task_type?: string; min_samples?: number } = {}): Promise<any> {
    return this.request("GET", "/v1/quality/leaderboard", undefined, {
      task_type: "chat",
      ...opts,
    });
  }

  async getQuality(modelId: string, taskType: string = "chat"): Promise<any> {
    return this.request("GET", `/v1/quality/${modelId}`, undefined, {
      task_type: taskType,
    });
  }

  // ─── Cache ────────────────────────────────────────────────────────

  async cacheStats(): Promise<any> {
    return this.request("GET", "/v1/cache/stats");
  }

  async cacheInvalidate(modelId?: string): Promise<any> {
    return this.request("DELETE", "/v1/cache", undefined, modelId ? { model_id: modelId } : undefined);
  }

  // ─── PII ──────────────────────────────────────────────────────────

  async piiDetect(text: string): Promise<any> {
    return this.request("POST", "/v1/pii/detect", { text });
  }

  async piiRedact(messages: Message[]): Promise<any> {
    return this.request("POST", "/v1/pii/redact", { messages });
  }

  async piiPatterns(): Promise<any> {
    return this.request("GET", "/v1/pii/patterns");
  }

  // ─── Agents ───────────────────────────────────────────────────────

  async registerAgent(
    agentId: string,
    opts: { name?: string; budget_cents?: number } = {},
  ): Promise<any> {
    return this.request("POST", "/v1/agents", { agent_id: agentId, ...opts });
  }

  async listAgents(opts: { status?: string } = {}): Promise<any> {
    return this.request("GET", "/v1/agents", undefined, opts.status ? { status: opts.status } : undefined);
  }

  async killAgent(agentId: string): Promise<any> {
    return this.request("POST", `/v1/agents/${agentId}/kill`);
  }

  async pauseAgent(agentId: string): Promise<any> {
    return this.request("POST", `/v1/agents/${agentId}/pause`);
  }

  async resumeAgent(agentId: string): Promise<any> {
    return this.request("POST", `/v1/agents/${agentId}/resume`);
  }

  // ─── Usage & Stats ────────────────────────────────────────────────

  async usage(opts: { limit?: number; agent_id?: string } = {}): Promise<any> {
    return this.request("GET", "/v1/usage", undefined, { limit: 50, ...opts });
  }

  async stats(): Promise<any> {
    return this.request("GET", "/v1/stats");
  }
}

export class SwiftGateError extends Error {
  status: number;
  response?: Response;

  constructor(message: string, status: number, response?: Response) {
    super(message);
    this.name = "SwiftGateError";
    this.status = status;
    this.response = response;
  }
}
