// Shared types for the financial agent frontend
export interface SourceLocation {
  doc_id: string;
  page: number;
  table_or_figure: string;
  row_col_or_line: string;
}

export interface ExtractedFigure {
  value: number | null;
  unit: string;
  name: string;
  source_loc: SourceLocation;
  confidence: 'high' | 'medium' | 'low' | 'unverified';
}

export interface Citation {
  doc_id: string;
  section: string;
  page: number;
  figure_refs: string[];
}

export interface ComputationResult {
  result: number | null;
  formula: string;
  inputs_with_sources: ExtractedFigure[];
  unit: string;
  metric: string;
  error: string | null;
}

export interface Anomaly {
  description: string;
  severity: 'info' | 'warning' | 'critical';
  source: SourceLocation | null;
  metric: string;
  change_value: number;
}

export interface GuardrailEvent {
  timestamp: string;
  original_text: string;
  rewritten_text: string;
  trigger_keywords: string[];
}

export interface TradeDraft {
  ticker: string;
  direction: 'long' | 'short' | 'neutral';
  thesis: string;
  risk_flags: string[];
  suggested_position_size: number | null;
  timestamp: string;
}

export interface AnalysisResponse {
  response: string;
  citations: Citation[];
  anomalies: Anomaly[];
  computations: ComputationResult[];
  trade_draft: TradeDraft | null;
}

export interface AnalysisRequest {
  query: string;
  document_ids: string[];
  thread_id?: string;
}

export interface TradeRequest {
  ticker: string;
  direction: 'long' | 'short' | 'neutral';
}

export interface Document {
  doc_id: string;
  filename: string;
  doc_type: string;
  chunks: number;
}