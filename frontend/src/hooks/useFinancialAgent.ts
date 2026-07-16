import { useState, useCallback, useEffect } from 'react';
import { apiService } from '../services/api';

interface Document {
  doc_id: string;
  filename: string;
  doc_type: string;
}

export function useDocuments() {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchDocuments = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const docs = await apiService.getDocuments();
      setDocuments(docs);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch documents');
    } finally {
      setLoading(false);
    }
  }, []);

  const uploadDocument = useCallback(async (file: File) => {
    try {
      setError(null);
      await apiService.uploadDocument(file);
      await fetchDocuments();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed');
      throw err;
    }
  }, [fetchDocuments]);

  useEffect(() => {
    fetchDocuments();
  }, [fetchDocuments]);

  return { documents, loading, error, uploadDocument, refreshDocuments: fetchDocuments };
}

interface AnalysisResponse {
  response: string;
  citations: any[];
  anomalies: any[];
  computations: any[];
  trade_draft?: any;
}

export function useAnalysis() {
  const [response, setResponse] = useState<AnalysisResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const queryAnalysis = useCallback(async (query: string, documentIds: string[]) => {
    try {
      setLoading(true);
      setError(null);
      const result = await apiService.queryAnalysis({ query, document_ids: documentIds });
      setResponse(result);
      return result;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Analysis failed');
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  const streamResponse = useCallback(async (
    query: string, 
    documentIds: string[], 
    onChunk: (chunk: any) => void
  ) => {
    try {
      setStreaming(true);
      setError(null);
      
      // Use WebSocket for streaming
      // This is a simplified version - in practice you'd use the WebSocket service
      const result = await apiService.queryAnalysis({ query, document_ids: documentIds });
      onChunk({ type: 'token', content: result.response });
      onChunk({ type: 'citations', metadata: { citations: result.citations } });
      onChunk({ type: 'anomalies', metadata: { anomalies: result.anomalies } });
      onChunk({ type: 'computations', metadata: { computations: result.computations } });
      onChunk({ type: 'done' });
      
      setResponse(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Streaming failed');
      throw err;
    } finally {
      setStreaming(false);
    }
  }, []);

  const clearResponse = useCallback(() => {
    setResponse(null);
    setError(null);
  }, []);

  return { 
    response, 
    loading, 
    streaming, 
    error, 
    queryAnalysis, 
    streamResponse, 
    clearResponse 
  };
}

export function useTradeTool() {
  const [tradeDraft, setTradeDraft] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const createDraft = useCallback(async (ticker: string, direction: 'long' | 'short' | 'neutral') => {
    try {
      setLoading(true);
      setError(null);
      const draft = await apiService.createTradeDraft({ ticker, direction });
      setTradeDraft(draft);
      return draft;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create trade draft');
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  const confirmDraft = useCallback(async (draftId: string) => {
    try {
      setLoading(true);
      setError(null);
      await apiService.confirmTrade(draftId);
      if (tradeDraft) {
        setTradeDraft({ ...tradeDraft, confirmed: true, confirmed_at: new Date().toISOString() });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to confirm trade draft');
      throw err;
    } finally {
      setLoading(false);
    }
  }, [tradeDraft]);

  return { tradeDraft, loading, error, createDraft, confirmDraft, setTradeDraft };
}

export function useAuditLogs() {
  const [guardrailLogs, setGuardrailLogs] = useState<any[]>([]);
  const [tradeDrafts, setTradeDrafts] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchGuardrailLogs = useCallback(async (startDate?: string, endDate?: string) => {
    try {
      setLoading(true);
      setError(null);
      const logs = await apiService.getGuardrailLogs({ start_date: startDate, end_date: endDate });
      setGuardrailLogs(logs);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch guardrail logs');
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchTradeDrafts = useCallback(async (userId?: string) => {
    try {
      setLoading(true);
      setError(null);
      const drafts = await apiService.getTradeDrafts({ user_id: userId });
      setTradeDrafts(drafts);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch trade drafts');
    } finally {
      setLoading(false);
    }
  }, []);

  return { 
    guardrailLogs, 
    tradeDrafts, 
    loading, 
    error, 
    fetchGuardrailLogs, 
    fetchTradeDrafts 
  };
}