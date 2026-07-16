import React, { useState } from 'react';
import { useDocuments, useAnalysis, useTradeTool } from '../hooks/useFinancialAgent';
import { AnalysisChat } from './Analysis/AnalysisChat';
import { TradeDraftCard } from './TradeTool/TradeDraftCard';
import { DocumentUploader } from './DocumentUploader';

export function Dashboard() {
  const { documents, loading: docsLoading, uploadDocument, refreshDocuments } = useDocuments();
  const {
    response,
    loading: analysisLoading,
    streaming,
    error: analysisError,
    queryAnalysis,
  } = useAnalysis();
  const { tradeDraft, loading: tradeLoading, createDraft, confirmDraft } = useTradeTool();
  
  const [showTradeDraft, setShowTradeDraft] = useState(false);

  const handleAnalyze = (query: string) => {
    const docIds = documents.map(d => d.doc_id);
    if (query.startsWith('/trade')) {
      const parts = query.split(' ');
      if (parts.length >= 3) {
        const ticker = parts[1];
        const direction = parts[2] as 'long' | 'short' | 'neutral';
        // First analyze, then create trade draft
        queryAnalysis(query.replace('/trade ', ''), docIds);
        setTimeout(() => createDraft(ticker, direction), 1000);
      }
    } else {
      queryAnalysis(query, docIds);
    }
  };

  const handleTradeDraft = (ticker: string, direction: 'long' | 'short' | 'neutral') => {
    createDraft(ticker, direction);
    setShowTradeDraft(true);
  };

  if (docsLoading) {
    return <div className="loading-spinner">Loading...</div>;
  }

  return (
    <div className="dashboard">
      <header className="dashboard-header">
        <div className="header-content">
          <h1>Financial Insight Agent</h1>
          <p>Analyze financial reports with grounded citations and safe computations</p>
        </div>
        <div className="header-actions">
          <button className="btn btn-primary" onClick={() => refreshDocuments()}>
            Refresh
          </button>
        </div>
      </header>

      <main className="dashboard-main">
        <div className="dashboard-grid">
          <aside className="sidebar">
            <section className="sidebar-section">
              <DocumentUploader onUpload={uploadDocument} />
            </section>

            <section className="sidebar-section">
              <h3>Documents ({documents.length})</h3>
              <ul className="document-list">
                {documents.map(doc => (
                  <li key={doc.doc_id} className="document-item">
                    <div className="doc-info">
                      <span className="doc-name">{doc.filename}</span>
                      <span className="doc-type">{doc.doc_type}</span>
                    </div>
                  </li>
                ))}
                {documents.length === 0 && (
                  <li className="empty-state">No documents uploaded</li>
                )}
              </ul>
            </section>
          </aside>

          <div className="main-content">
            <AnalysisChat
              documents={documents}
              selectedDocIds={documents.map(d => d.doc_id)}
              onAnalyze={handleAnalyze}
              onTradeDraft={handleTradeDraft}
              loading={analysisLoading}
              streaming={streaming}
              response={response}
              error={analysisError}
            />

            {showTradeDraft && tradeDraft && (
              <TradeDraftCard
                draft={tradeDraft}
                onConfirm={() => {
                  confirmDraft(tradeDraft.timestamp);
                  setShowTradeDraft(false);
                }}
                onCancel={() => setShowTradeDraft(false)}
                loading={tradeLoading}
              />
            )}

            {analysisError && (
              <div className="alert alert-error">
                {analysisError}
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}

export default Dashboard;