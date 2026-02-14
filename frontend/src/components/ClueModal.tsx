import { useState, useEffect, useRef } from 'react';
import type { ClueDetail, AnswerResult } from '../types';
import { fetchClue, submitAnswer } from '../api';

interface Props {
  clueId: number;
  value: number;
  isDailyDouble: boolean;
  currentScore: number;
  roundMax: number;
  onClose: (result: { correct: boolean; value: number } | null) => void;
}

type Phase = 'loading' | 'wager' | 'clue' | 'result';

export default function ClueModal({ clueId, value, isDailyDouble, currentScore, roundMax, onClose }: Props) {
  const [phase, setPhase] = useState<Phase>('loading');
  const [clue, setClue] = useState<ClueDetail | null>(null);
  const [response, setResponse] = useState('');
  const [result, setResult] = useState<AnswerResult | null>(null);
  const [wager, setWager] = useState(value);
  const [wagerInput, setWagerInput] = useState(String(value));
  const inputRef = useRef<HTMLInputElement>(null);

  const effectiveValue = isDailyDouble ? wager : value;

  useEffect(() => {
    fetchClue(clueId).then((data) => {
      setClue(data);
      setPhase(isDailyDouble ? 'wager' : 'clue');
    });
  }, [clueId, isDailyDouble]);

  useEffect(() => {
    if ((phase === 'clue' || phase === 'wager') && inputRef.current) {
      inputRef.current.focus();
    }
  }, [phase]);

  const maxWager = Math.max(currentScore, roundMax);

  const handleWagerSubmit = () => {
    const parsed = parseInt(wagerInput, 10);
    if (isNaN(parsed) || parsed < 5 || parsed > maxWager) return;
    setWager(parsed);
    setPhase('clue');
  };

  const handleSubmit = async () => {
    if (!response.trim()) return;
    const res = await submitAnswer(clueId, response);
    setResult(res);
    setPhase('result');
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      if (phase === 'wager') handleWagerSubmit();
      else if (phase === 'clue') handleSubmit();
      else if (phase === 'result') onClose(result ? { correct: result.correct, value: effectiveValue } : null);
    }
  };

  return (
    <div className="modal-overlay" onClick={() => phase === 'result' && onClose(result ? { correct: result.correct, value: effectiveValue } : null)}>
      <div className="modal" onClick={(e) => e.stopPropagation()} onKeyDown={handleKeyDown}>
        {phase === 'loading' && <div className="modal-loading">Loading...</div>}

        {phase === 'wager' && (
          <div className="modal-wager">
            <div className="dd-banner">DAILY DOUBLE!</div>
            <div className="wager-prompt">
              Enter your wager (5 - ${maxWager.toLocaleString()}):
            </div>
            <input
              ref={inputRef}
              type="number"
              min={5}
              max={maxWager}
              value={wagerInput}
              onChange={(e) => setWagerInput(e.target.value)}
              className="wager-input"
            />
            <button onClick={handleWagerSubmit} className="submit-btn">Set Wager</button>
          </div>
        )}

        {phase === 'clue' && clue && (
          <div className="modal-clue">
            <div className="clue-category">{clue.category} - ${effectiveValue}</div>
            <div className="clue-text">{clue.clue_text}</div>
            <input
              ref={inputRef}
              type="text"
              value={response}
              onChange={(e) => setResponse(e.target.value)}
              placeholder="What is..."
              className="response-input"
            />
            <button onClick={handleSubmit} className="submit-btn">Submit</button>
          </div>
        )}

        {phase === 'result' && result && (
          <div className="modal-result">
            <div className={`result-banner ${result.correct ? 'correct' : 'incorrect'}`}>
              {result.correct ? 'CORRECT!' : 'INCORRECT'}
            </div>
            <div className="expected">
              {result.correct ? '' : `Correct response: ${result.expected}`}
            </div>
            <div className="result-value">
              {result.correct ? '+' : '-'}${effectiveValue.toLocaleString()}
            </div>
            <button onClick={() => onClose({ correct: result.correct, value: effectiveValue })} className="submit-btn">
              Continue
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
