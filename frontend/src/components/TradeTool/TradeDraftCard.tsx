import React from 'react';

interface TradeDraftCardProps {
  draft: {
    ticker: string;
    direction: 'long' | 'short' | 'neutral';
    thesis: string;
    riskFlags: string[];
    suggestedPositionSize?: number;
    timestamp: string;
  };
  onConfirm: () => void;
  onCancel: () => void;
  loading?: boolean;
}

export function TradeDraftCard({ draft, onConfirm, onCancel, loading }: TradeDraftCardProps) {
  const directionColors = {
    long: 'text-green-600 bg-green-100',
    short: 'text-red-600 bg-red-100',
    neutral: 'text-gray-600 bg-gray-100',
  };

  return (
    <div className="trade-draft-card border rounded-lg p-6 bg-white shadow-sm">
      <div className="flex justify-between items-start mb-4">
        <h3 className="text-xl font-semibold">Trade Draft</h3>
        <span className={`px-2 py-1 rounded text-sm font-medium ${directionColors[draft.direction]}`}>
          {draft.direction.toUpperCase()}
        </span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
        <div>
          <label className="block text-sm font-medium text-gray-500 mb-1">Ticker</label>
          <p className="text-lg font-mono">{draft.ticker}</p>
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-500 mb-1">Created</label>
          <p className="text-sm text-gray-600">{new Date(draft.timestamp).toLocaleString()}</p>
        </div>
      </div>

      <div className="mb-4">
        <label className="block text-sm font-medium text-gray-500 mb-1">Investment Thesis</label>
        <p className="text-gray-800 whitespace-pre-wrap">{draft.thesis}</p>
      </div>

      {draft.riskFlags.length > 0 && (
        <div className="mb-4">
          <label className="block text-sm font-medium text-gray-500 mb-1">Risk Flags</label>
          <div className="flex flex-wrap gap-2">
            {draft.riskFlags.map((flag, i) => (
              <span key={i} className="px-2 py-1 bg-yellow-100 text-yellow-800 rounded text-sm">
                {flag}
              </span>
            ))}
          </div>
        </div>
      )}

      {draft.suggestedPositionSize && (
        <div className="mb-4 p-3 bg-blue-50 rounded">
          <label className="block text-sm font-medium text-gray-500 mb-1">Suggested Position Size</label>
          <p className="text-lg font-semibold text-blue-800">{draft.suggestedPositionSize}%</p>
          <p className="text-xs text-blue-600 mt-1">Based on risk parameters and detected anomalies</p>
        </div>
      )}

      <div className="border-t pt-4 flex gap-3">
        <button
          onClick={onCancel}
          disabled={loading}
          className="flex-1 px-4 py-2 border rounded-lg text-gray-700 hover:bg-gray-50 disabled:opacity-50"
        >
          Cancel
        </button>
        <button
          onClick={onConfirm}
          disabled={loading}
          className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
        >
          {loading ? 'Confirming...' : 'Confirm Draft'}
        </button>
      </div>

      <p className="mt-4 text-xs text-gray-500 text-center">
        ⚠️ This is a draft only. No order will be placed. Submit manually through your brokerage.
      </p>
    </div>
  );
}

export default TradeDraftCard;