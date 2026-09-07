import { useState } from 'react';

import { askPolicyQuestion } from '../api.js';

export default function PolicyAssistantChat() {
  const [open, setOpen] = useState(false);
  const [question, setQuestion] = useState('');
  const [messages, setMessages] = useState([]);
  const [asking, setAsking] = useState(false);
  const [error, setError] = useState('');

  async function handleSubmit(event) {
    event.preventDefault();
    const trimmed = question.trim();
    if (!trimmed) return;

    setAsking(true);
    setError('');
    try {
      const result = await askPolicyQuestion(trimmed);
      setMessages((prev) => [...prev, { question: trimmed, ...result }]);
      setQuestion('');
    } catch (err) {
      setError(err.message || 'Could not reach the assistant. Please try again.');
    } finally {
      setAsking(false);
    }
  }

  return (
    <div className="policy-assistant">
      <button type="button" className="policy-assistant__toggle" onClick={() => setOpen((v) => !v)}>
        💬 Ask about onboarding {open ? '▲' : '▼'}
      </button>

      {open && (
        <div className="policy-assistant__panel">
          <p className="policy-assistant__hint">
            Ask about required documents, timelines, or account types. This assistant only answers from our policy
            documents — it can't tell you the status of your own application.
          </p>

          {messages.length > 0 && (
            <div className="policy-assistant__messages">
              {messages.map((msg, index) => (
                <div key={index} className="policy-assistant__message">
                  <p className="policy-assistant__question">You asked: {msg.question}</p>
                  <p
                    className={`policy-assistant__answer policy-assistant__answer--${msg.status.toLowerCase()}`}
                    role="status"
                  >
                    {msg.answer}
                  </p>
                  {msg.citations.length > 0 && (
                    <ul className="policy-assistant__citations">
                      {msg.citations.map((citation, citationIndex) => (
                        <li key={citationIndex}>
                          Source: {citation.source_document} — {citation.section_reference}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              ))}
            </div>
          )}

          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}

          <form className="policy-assistant__form" onSubmit={handleSubmit}>
            <input
              type="text"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="e.g. What documents do I need?"
              disabled={asking}
              aria-label="Ask the onboarding assistant a question"
            />
            <button type="submit" disabled={asking || !question.trim()}>
              {asking ? 'Asking…' : 'Ask'}
            </button>
          </form>
        </div>
      )}
    </div>
  );
}
