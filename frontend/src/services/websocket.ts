// WebSocket service for real-time analysis streaming
import type { AnalysisResponse, Citation, Anomaly, ComputationResult } from '../types/financial-agent';

export type WebSocketMessageType = 
  | 'token' 
  | 'citations' 
  | 'anomalies' 
  | 'computation' 
  | 'done' 
  | 'error';

export interface WebSocketMessage {
  type: WebSocketMessageType;
  content?: string;
  metadata?: {
    citations?: Citation[];
    anomalies?: Anomaly[];
    computation?: ComputationResult;
  };
}

export interface AnalysisStreamRequest {
  type: 'analysis_query';
  query: string;
  document_ids: string[];
  thread_id: string;
}

class WebSocketService {
  private ws: WebSocket | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 3;
  private reconnectDelay = 1000;
  private messageHandlers: Map<WebSocketMessageType, (message: WebSocketMessage) => void> = new Map();
  private onOpenCallback?: () => void;
  private onCloseCallback?: () => void;
  private onErrorCallback?: (error: Event) => void;

  connect(url: string = 'ws://localhost/ws/analysis/stream'): Promise<void> {
    return new Promise((resolve, reject) => {
      try {
        this.ws = new WebSocket(url);

        this.ws.onopen = () => {
          console.log('WebSocket connected');
          this.reconnectAttempts = 0;
          this.onOpenCallback?.();
          resolve();
        };

        this.ws.onmessage = (event) => {
          try {
            const message: WebSocketMessage = JSON.parse(event.data);
            const handler = this.messageHandlers.get(message.type);
            if (handler) {
              handler(message);
            }
          } catch (error) {
            console.error('Failed to parse WebSocket message:', error);
          }
        };

        this.ws.onclose = () => {
          console.log('WebSocket disconnected');
          this.onCloseCallback?.();
          this.attemptReconnect(url);
        };

        this.ws.onerror = (error) => {
          console.error('WebSocket error:', error);
          this.onErrorCallback?.(error);
          reject(error);
        };
      } catch (error) {
        reject(error);
      }
    });
  }

  private attemptReconnect(url: string) {
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.reconnectAttempts++;
      setTimeout(() => {
        console.log(`Reconnecting... (attempt ${this.reconnectAttempts})`);
        this.connect(url).catch(() => {});
      }, this.reconnectDelay * this.reconnectAttempts);
    }
  }

  disconnect() {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }

  sendAnalysisRequest(request: AnalysisStreamRequest) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(request));
    } else {
      throw new Error('WebSocket not connected');
    }
  }

  onMessage(type: WebSocketMessageType, handler: (message: WebSocketMessage) => void) {
    this.messageHandlers.set(type, handler);
  }

  onOpen(callback: () => void) {
    this.onOpenCallback = callback;
  }

  onClose(callback: () => void) {
    this.onCloseCallback = callback;
  }

  onError(callback: (error: Event) => void) {
    this.onErrorCallback = callback;
  }

  isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }
}

export const wsService = new WebSocketService();