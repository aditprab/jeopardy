import { useState, useEffect, useRef } from 'react';
import type { ClueDetail, AnswerResult, AppealResult } from '../types';
import { fetchClue, submitAnswer, submitAppeal } from '../api';

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
  const [skipped, setSkipped] = useState(false);
  const [appealText, setAppealText] = useState('');
  const [appealLoading, setAppealLoading] = useState(false);
  const [appealError, setAppealError] = useState('');
  const [appealResult, setAppealResult] = useState<AppealResult | null>(null);
  const [wager, setWager] = useState(value);
  const [wagerInput, setWagerInput] = useState(String(value));
  const inputRef = useRef<HTMLInputElement>(null);

  const effectiveValue = isDailyDouble ? wager : value;

  useEffect(() => {
    fetchClue(clueId).then((data) => {
      setClue(data);
      setPhase(isDailyDouble ? 'wager' : 'clue');
    });
    setAppealText('');
    setAppealLoading(false);
    setAppealError('');
    setAppealResult(null);
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
    setAppealText('');
    setAppealError('');
    setAppealResult(null);
    setPhase('result');
  };

  const handleSkip = () => {
    setSkipped(true);
    setResult({ correct: false, expected: clue?.expected_response ?? '' });
    setAppealText('');
    setAppealError('');
    setAppealResult(null);
    setPhase('result');
  };

  const handleAppeal = async () => {
    if (!result?.attempt_id || appealLoading) return;
    setAppealLoading(true);
    setAppealError('');
    try {
      const appeal = await submitAppeal(result.attempt_id, appealText.trim() || undefined);
      setAppealResult(appeal);
      setResult((prev) => (prev ? { ...prev, correct: appeal.final_correct } : prev));
    } catch {
      setAppealError('Appeal failed. Please try again.');
    } finally {
      setAppealLoading(false);
    }
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
            <div className="clue-buttons">
              <button onClick={handleSubmit} className="submit-btn">Submit</button>
              {!isDailyDouble && <button onClick={handleSkip} className="skip-btn">Skip</button>}
            </div>
          </div>
        )}

        {phase === 'result' && result && (
          <div className="modal-result">
            <div className={`result-banner ${result.correct ? 'correct' : skipped ? 'skipped' : 'incorrect'}`}>
              {result.correct ? 'CORRECT!' : skipped ? 'SKIPPED' : 'INCORRECT'}
            </div>
            <div className="expected">
              {result.correct ? '' : `Correct response: ${result.expected}`}
            </div>
            {!skipped && (
              <div className="result-value">
                {result.correct ? '+' : '-'}${effectiveValue.toLocaleString()}
              </div>
            )}
            {!result.correct && !skipped && result.attempt_id && (
              <div className="appeal-block">
                {!appealResult && (
                  <>
                    <textarea
                      value={appealText}
                      onChange={(e) => setAppealText(e.target.value)}
                      placeholder="Optional: Why should this response count?"
                      className="appeal-input"
                      maxLength={280}
                    />
                    <button onClick={handleAppeal} className="appeal-btn" disabled={appealLoading}>
                      {appealLoading ? 'Reviewing...' : 'Appeal to Judge Agent'}
                    </button>
                  </>
                )}
                {appealError && <div className="appeal-error">{appealError}</div>}
                {appealResult && (
                  <div className={`appeal-result ${appealResult.overturn ? 'overturned' : 'denied'}`}>
                    {appealResult.overturn ? 'Appeal Accepted' : 'Appeal Denied'}: {appealResult.reason}
                  </div>
                )}
              </div>
            )}
            <button onClick={() => onClose({ correct: result.correct, value: skipped ? 0 : effectiveValue })} className="submit-btn">
              Continue
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
