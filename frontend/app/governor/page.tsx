'use client';

import { useState, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import { usePersona } from '@/hooks/usePersona';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  sources?: Array<{ type: string; id: string }>;
  proposal?: BeliefProposal;
}

interface BeliefProposal {
  type: string;
  belief_id: string;
  current_confidence: number;
  proposed_confidence: number;
  reason: string;
  evidence: string[];
}

export default function GovernorPage() {
  const { selectedPersonaId } = usePersona();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [activeProposal, setActiveProposal] = useState<BeliefProposal | null>(null);

  const suggestions = [
    "Why did you change your stance on climate change?",
    "Show interactions about cryptocurrency from last month",
    "Explain your current belief about nuclear energy",
    "What evidence supports your stance on electric vehicles?",
  ];

  const handleSubmit = async (question: string) => {
    if (!selectedPersonaId) {
      alert('Please select a persona first');
      return;
    }

    setLoading(true);
    setMessages((prev) => [...prev, { role: 'user', content: question }]);
    setInput('');

    try {
      const token = typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null;
      const response = await fetch('http://localhost:8000/api/v1/governor/query', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          persona_id: selectedPersonaId,
          question,
        }),
      });

      if (!response.ok) {
        throw new Error(`Query failed: ${response.statusText}`);
      }

      const data = await response.json();

      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: data.answer,
          sources: data.sources,
          proposal: data.proposal,
        },
      ]);

      if (data.proposal) {
        setActiveProposal(data.proposal);
      }
    } catch (error) {
      console.error('Governor query failed:', error);
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: `Error: ${error instanceof Error ? error.message : 'Unknown error'}`,
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleApproveProposal = async (approve: boolean) => {
    if (!activeProposal || !selectedPersonaId) return;

    try {
      const token = typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null;
      const response = await fetch('http://localhost:8000/api/v1/governor/approve-proposal', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          persona_id: selectedPersonaId,
          belief_id: activeProposal.belief_id,
          proposed_confidence: activeProposal.proposed_confidence,
          reason: activeProposal.reason,
          approved: approve,
        }),
      });

      if (!response.ok) {
        throw new Error(`Approval failed: ${response.statusText}`);
      }

      const data = await response.json();

      if (approve) {
        alert(`Belief updated successfully: ${data.message}`);
      } else {
        alert('Proposal rejected');
      }

      setActiveProposal(null);
    } catch (error) {
      console.error('Proposal approval failed:', error);
      alert(`Error: ${error instanceof Error ? error.message : 'Unknown error'}`);
    }
  };

  return (
    <div className="container mx-auto max-w-4xl p-6">
      <div className="mb-6">
        <h1 className="text-3xl font-bold text-[var(--text-primary)] mb-2">
          Governor Chat
        </h1>
        <p className="text-[var(--text-secondary)]">
          Query the agent&apos;s reasoning, belief evolution, and past interactions
        </p>
      </div>

      {/* Persona Selector */}
      {!selectedPersonaId && (
        <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4 mb-4">
          <p className="text-sm text-yellow-800">
            Please select a persona from the header to start querying.
          </p>
        </div>
      )}

      {/* Suggestions */}
      {messages.length === 0 && selectedPersonaId && (
        <div className="mb-6 bg-white rounded-lg border border-[var(--border)] p-6">
          <p className="text-sm font-semibold text-[var(--text-secondary)] mb-3">
            Try asking:
          </p>
          <div className="grid gap-2">
            {suggestions.map((suggestion) => (
              <button
                key={suggestion}
                onClick={() => handleSubmit(suggestion)}
                disabled={loading}
                className="text-left p-3 hover:bg-gray-50 rounded-lg border border-transparent hover:border-[var(--border)] transition-all text-sm text-[var(--text-primary)]"
              >
                {suggestion}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Chat History */}
      <div className="space-y-4 mb-6 max-h-[500px] overflow-y-auto">
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`p-4 rounded-lg ${
              msg.role === 'user'
                ? 'bg-blue-50 border border-blue-200'
                : 'bg-gray-50 border border-[var(--border)]'
            }`}
          >
            <div className="flex items-center gap-2 mb-2">
              <span className="font-semibold text-sm">
                {msg.role === 'user' ? 'You' : 'Governor'}
              </span>
              {msg.role === 'assistant' && msg.sources && msg.sources.length > 0 && (
                <span className="text-xs text-[var(--text-secondary)]">
                  {msg.sources.length} source{msg.sources.length > 1 ? 's' : ''} cited
                </span>
              )}
            </div>
            <div className="prose prose-sm max-w-none text-[var(--text-primary)] prose-p:text-[var(--text-primary)] prose-strong:text-[var(--text-primary)] prose-li:text-[var(--text-primary)]">
              <ReactMarkdown>{msg.content}</ReactMarkdown>
            </div>
            {msg.sources && msg.sources.length > 0 && (
              <div className="mt-3 pt-3 border-t border-gray-200">
                <p className="text-xs font-semibold text-[var(--text-secondary)] mb-1">
                  Sources:
                </p>
                <div className="flex flex-wrap gap-2">
                  {msg.sources.map((source, idx) => (
                    <span
                      key={idx}
                      className="text-xs bg-white px-2 py-1 rounded border border-[var(--border)]"
                    >
                      {source.type}: {source.id.slice(0, 8)}...
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Active Proposal Card */}
      {activeProposal && (
        <div className="mb-6 bg-yellow-50 border-2 border-yellow-400 rounded-lg p-6">
          <h3 className="font-bold text-lg text-yellow-900 mb-3">
            Belief Adjustment Proposal
          </h3>
          <div className="space-y-2 text-sm text-yellow-900 mb-4">
            <p>
              <span className="font-semibold">Belief ID:</span> {activeProposal.belief_id}
            </p>
            <p>
              <span className="font-semibold">Current confidence:</span>{' '}
              {activeProposal.current_confidence.toFixed(2)}
            </p>
            <p>
              <span className="font-semibold">Proposed confidence:</span>{' '}
              {activeProposal.proposed_confidence.toFixed(2)}
            </p>
            <p>
              <span className="font-semibold">Reason:</span> {activeProposal.reason}
            </p>
            {activeProposal.evidence.length > 0 && (
              <p>
                <span className="font-semibold">Evidence:</span>{' '}
                {activeProposal.evidence.length} interaction(s)
              </p>
            )}
          </div>
          <div className="flex gap-3">
            <button
              onClick={() => handleApproveProposal(true)}
              className="px-4 py-2 bg-green-600 text-white rounded-lg font-semibold hover:bg-green-700 transition-colors"
            >
              Approve
            </button>
            <button
              onClick={() => handleApproveProposal(false)}
              className="px-4 py-2 bg-red-600 text-white rounded-lg font-semibold hover:bg-red-700 transition-colors"
            >
              Reject
            </button>
          </div>
        </div>
      )}

      {/* Input Area */}
      {selectedPersonaId && (
        <div className="bg-white rounded-lg border border-[var(--border)] p-4">
          <div className="flex gap-3">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey && input.trim()) {
                  e.preventDefault();
                  handleSubmit(input);
                }
              }}
              placeholder="Ask about the agent's reasoning..."
              className="flex-1 px-4 py-2 border border-[var(--border)] rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--primary)] text-[var(--text-primary)]"
              disabled={loading}
            />
            <button
              onClick={() => handleSubmit(input)}
              disabled={loading || !input.trim()}
              className="px-6 py-2 bg-[var(--primary)] text-white rounded-lg font-semibold hover:opacity-90 transition-opacity disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? 'Thinking...' : 'Ask'}
            </button>
          </div>
          <p className="text-xs text-[var(--text-secondary)] mt-2">
            Press Enter to send, Shift+Enter for new line
          </p>
        </div>
      )}
    </div>
  );
}
