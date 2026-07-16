// API Service for Financial Insight Agent

const API_BASE = '/api';

interface AnalysisRequest {
  query: string;
  document_ids: string[];
  thread_id?: string;
}

interface TradeRequest {
  ticker: string;
  direction: 'long' | 'short' | 'neutral';
}

interface GuardrailLogParams {
  start_date?: string;
  end_date?: string;
}

interface TradeDraftParams {
  user_id?: string;
}

class ApiService {
  private async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const response = await fetch(`${API_BASE}${endpoint}`, {
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
      ...options,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: 'Unknown error' }));
      throw new Error(error.error || `HTTP ${response.status}`);
    }

    return response.json();
  }

  // Document endpoints
  async uploadDocument(file: File): Promise<{ doc_id: string; status: string; filename: string }> {
    const formData = new FormData();
    formData.append('file', file);
    
    const response = await fetch(`${API_BASE}/documents/upload`, {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: 'Unknown error' }));
      throw new Error(error.error || `HTTP ${response.status}`);
    }

    return response.json();
  }

  async getDocuments(): Promise<Array<{ doc_id: string; filename: string; doc_type: string }>> {
    return this.request('/documents');
  }

  async getDocument(docId: string): Promise<{ doc_id: string; filename: string; doc_type: string; chunks: number }> {
    return this.request(`/documents/${docId}`);
  }

  // Analysis endpoints
  async queryAnalysis(request: AnalysisRequest): Promise<{
    response: string;
    citations: any[];
    anomalies: any[];
    computations: any[];
    trade_draft?: any;
  }> {
    return this.request('/analysis/query', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  }

  // Trade endpoints
  async createTradeDraft(request: TradeRequest): Promise<any> {
    return this.request('/trade/draft', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  }

  async confirmTrade(draftId: string): Promise<{ status: string; draft_id: string; message: string }> {
    return this.request(`/trade/confirm/${draftId}`, {
      method: 'POST',
    });
  }

  // Audit endpoints
  async getGuardrailLogs(params: GuardrailLogParams = {}): Promise<any[]> {
    const searchParams = new URLSearchParams();
    if (params.start_date) searchParams.append('start_date', params.start_date);
    if (params.end_date) searchParams.append('end_date', params.end_date);
    
    return this.request(`/audit/guardrail-logs?${searchParams.toString()}`);
  }

  async getTradeDrafts(params: TradeDraftParams = {}): Promise<any[]> {
    const searchParams = new URLSearchParams();
    if (params.user_id) searchParams.append('user_id', params.user_id);
    
    return this.request(`/audit/trade-drafts?${searchParams.toString()}`);
  }

  // Admin endpoints
  async getSystemHealth(): Promise<{ status: string; components: Record<string, string> }> {
    return this.request('/admin/system-health');
  }
}

export const apiService = new ApiService();

// WebSocket service for streaming
export class WebSocketService {
  private ws: WebSocket | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 1000;

  connect(
    query: string,
    documentIds: string[],
    onMessage: (data: any) => void,
    onError: (error: Event) => void,
    onClose: () => void
  ): void {
    const wsUrl = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws/analysis/stream`;
    
    this.ws = new WebSocket(wsUrl);
    
    this.ws.onopen = () => {
      this.reconnectAttempts = 0;
      this.ws?.send(JSON.stringify({
        type: 'analysis_query',
        query,
        document_ids: documentIds,
        thread_id: crypto.randomUUID(),
      }));
    };

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        onMessage(data);
      } catch (error) {
        console.error('Failed to parse WebSocket message:', error);
      }
    };

    this.ws.onerror = (error) => {
      onError(error);
    };

    this.ws.onclose = () => {
      onClose();
      this.attemptReconnect(query, documentIds, onMessage, onError, onClose);
    };
  }

  private attemptReconnect(
    query: string,
    documentIds: string[],
    onMessage: (data: any) => void,
    onError: (error: Event) => void,
    onClose: () => void
  ): void {
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.reconnectAttempts++;
      setTimeout(() => {
        this.connect(query, documentIds, onMessage, onError, onClose);
      }, this.reconnectDelay * this.reconnectAttempts);
    }
  }

  disconnect(): void {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }

  send(data: any): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data));
    }
  }
}

export const wsService = new WebSocketService();