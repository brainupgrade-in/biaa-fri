import React, { useState, useEffect, useRef } from 'react';
import { AnalysisChatProps } from '../types/financial-agent';

interface AnalysisChatProps {
  documents: any[];
  selectedDocIds: string[];
  onAnalyze: (query: string) => void;
  onTradeDraft: (ticker: string, direction: 'long' | 'short' | 'neutral') => void;
  loading: boolean;
  streaming: boolean;
  response: any;
  error: string | null;
}

interface Message {
  id: string;
  type: 'user' | 'assistant';
  content: string;
  citations?: any[];
  anomalies?: any[];
  computations?: any[];
  timestamp: Date;
}

export function AnalysisChat({ 
  documents, 
  selectedDocIds, 
  onAnalyze, 
  onTradeDraft,
  loading, 
  streaming, 
  response, 
  error 
}: AnalysisChatProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [showSuggestions, setShowSuggestions] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (response) {
      const newMessage: Message = {
        id: crypto.randomUUID(),
        type: 'assistant',
        content: response.response || response.final_response || '',
        citations: response.citations,
        anomalies: response.anomalies,
        computations: response.computations,
        timestamp: new Date(),
      };
      setMessages(prev => [...prev, newMessage]);
    }
  }, [response]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || !selectedDocIds.length) return;

    const userMessage: Message = {
      id: crypto.randomUUID(),
      type: 'user',
      content: input,
      timestamp: new Date(),
    };
    
    setMessages(prev => [...prev, userMessage]);
    onAnalyze(input);
    setInput('');
    setShowSuggestions(false);
  };

  const handleTradeDraft = (ticker: string, direction: 'long' | 'short' | 'neutral') => {
    onTradeDraft(ticker, direction);
  };

  const suggestions = [
    "What was the revenue in the latest period?",
    "Calculate the current ratio",
    "Are there any anomalies in the margins?",
    "Summarize the key financial metrics",
    "What is the YoY revenue growth?",
    "Show me the cash flow statement",
  ];

  return (
    <div className="analysis-chat">
      <div className="chat-header">
        <h3>Analysis Chat</h3>
        <div className="chat-status">
          {selectedDocIds.length > 0 && (
            <span className="status-badge">{selectedDocIds.length} document(s) selected</span>
          )}
          {streaming && <span className="status-badge streaming">Analyzing...</span>}
        </div>
      </div>

      <div className="chat-messages" role="log" aria-live="polite">
        {messages.map(message => (
          <MessageBubble key={message.id} message={message} />
        ))}
        
        {streaming && (
          <div className="message assistant streaming">
            <div className="message-content">
              <span className="typing-indicator">
                <span></span><span></span><span></span>
              </span>
            </div>
          </div>
        )}

        {error && (
          <div className="message error">
            <div className="message-content error-content">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10"/>
                <line x1="15" y1="9" x2="9" y2="15"/>
                <line x1="9" y1="9" x2="15" y2="15"/>
              </svg>
              {error}
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      <div className="chat-input-area">
        {showSuggestions && !loading && !streaming && (
          <div className="suggestions">
            <p>Quick questions:</p>
            <div className="suggestion-chips">
              {suggestions.map((suggestion, i) => (
                <button
                  key={i}
                  className="suggestion-chip"
                  onClick={() => { setInput(suggestion); handleSubmit(new Event('submit')); }}
                >
                  {suggestion}
                </button>
              ))}
            </div>
          </div>
        )}

        <form onSubmit={handleSubmit} className="chat-form">
          <div className="input-wrapper">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onFocus={() => setShowSuggestions(true)}
              onBlur={() => setTimeout(() => setShowSuggestions(false), 200)}
              placeholder={selectedDocIds.length === 0 ? 'Select a document first...' : 'Ask about the financial report...'}
              disabled={loading || streaming || selectedDocIds.length === 0}
              rows={1}
              style={{ minHeight: '44px', maxHeight: '120px' }}
            />
            <button
              type="submit"
              className="send-button"
              disabled={loading || streaming || !input.trim() || selectedDocIds.length === 0}
              aria-label="Send message"
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <line x1="22" y1="2" x2="11" y2="13"/>
                <polygon points="22 2 15 22 11 13 2 9 22 2"/>
              </svg>
            </button>
          </div>
          
          {selectedDocIds.length > 0 && !loading && !streaming && (
            <div className="trade-trigger">
              <span>Quick actions:</span>
              <button 
                className="btn btn-outline btn-sm"
                onClick={() => handleTradeDraft('', 'long')}
              >
                Generate Trade Draft
              </button>
            </div>
          )}
        </form>
      </div>
    </div>
  );
}

function MessageBubble({ message }: { message: Message }) {
  const isUser = message.type === 'user';

  return (
    <div className={`message ${message.type}`}>
      <div className="message-content">
        {isUser ? (
          <p>{message.content}</p>
        ) : (
          <div>
            <ReactMarkdown content={message.content} />
            
            {message.computations && message.computations.length > 0 && (
              <div className="computations-section">
                {message.computations.map((comp: any, i: number) => (
                  <div key={i} className="computation-card">
                    <div className="computation-header">
                      <span className="computation-metric">{comp.metric}</span>
                      <span className="computation-formula">{comp.formula}</span>
                    </div>
                    <div className={comp.error ? 'computation-error' : 'computation-result'}>
                      {comp.error ? `Error: ${comp.error}` : comp.result !== null ? comp.result.toFixed(2) : 'N/A'}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {message.anomalies && message.anomalies.length > 0 && (
              <div className="anomalies-section">
                <h5>Anomaly Observations</h5>
                {message.anomalies.map((anomaly: any, i: number) => (
                  <div key={i} className={`anomaly-badge ${anomaly.severity}`}>
                    <span className="anomaly-severity">{anomaly.severity.toUpperCase()}</span>
                    <span>{anomaly.description}</span>
                    {anomaly.metric && <span className="anomaly-metric">{anomaly.metric}</span>}
                  </div>
                ))}
              </div>
            )}

            {message.citations && message.citations.length > 0 && (
              <div className="sources-section">
                <h5>Sources</h5>
                <ul>
                  {message.citations.map((cite: any, i: number) => (
                    <li key={i}>
                      [{cite.doc_id}] {cite.section} (p. {cite.page})
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>
      <div className="message-time">
        {message.timestamp.toLocaleTimeString()}
      </div>
    </div>
  );
}

// Simple ReactMarkdown replacement
function ReactMarkdown({ content }: { content: string }) {
  // Simple markdown rendering
  const html = content
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>')
    .replace(/`(.*?)`/g, '<code>$1</code>')
    .replace(/\n\n/g, '</p><p>')
    .replace(/\n/g, '<br/>');
  
  return <p dangerouslySetInnerHTML={{ __html: `<p>${html}</p>` }} />;
}

interface Message {
  id: string;
  type: 'user' | 'assistant';
  content: string;
  citations?: any[];
  anomalies?: any[];
  computations?: any[];
  timestamp: Date;
}