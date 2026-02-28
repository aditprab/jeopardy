import { useEffect, useMemo, useRef, useState } from 'react';
import {
  fetchDailyChallenge,
  submitDailyAnswer,
  submitDailyFinal,
  submitDailyFinalWager,
} from '../api';
import type {
  DailyChallengeData,
  DailyProgressAnswer,
  DailyAnswerResult,
  DailyFinalResult,
} from '../types';
import Scoreboard from './Scoreboard';

type Stage = 'single' | 'double' | 'final' | 'done';

interface DailyChallengeGameProps {
  onBack: () => void;
}

function formatAirDate(isoDate: string): string {
  const d = new Date(`${isoDate}T00:00:00`);
  if (Number.isNaN(d.getTime())) return isoDate;
  return d.toLocaleDateString('en-US', {
    month: 'long',
    day: 'numeric',
    year: 'numeric',
  });
}

function ordinal(day: number): string {
  if (day >= 11 && day <= 13) return `${day}th`;
  const mod = day % 10;
  if (mod === 1) return `${day}st`;
  if (mod === 2) return `${day}nd`;
  if (mod === 3) return `${day}rd`;
  return `${day}th`;
}

function formatChallengeDate(isoDate: string): string {
  const d = new Date(`${isoDate}T00:00:00`);
  if (Number.isNaN(d.getTime())) return isoDate;
  const month = d.toLocaleDateString('en-US', { month: 'long' });
  const day = ordinal(d.getDate());
  const year = d.getFullYear();
  return `${month} ${day}, ${year}`;
}

function nextStep(data: DailyChallengeData): { stage: Stage; index: number } {
  for (let i = 0; i < 5; i += 1) {
    if (!data.progress.answers.single[i]) {
      return { stage: 'single', index: i };
    }
  }
  for (let i = 0; i < 5; i += 1) {
    if (!data.progress.answers.double[i]) {
      return { stage: 'double', index: i };
    }
  }
  if (!data.progress.final.submitted) {
    return { stage: 'final', index: 0 };
  }
  return { stage: 'done', index: 0 };
}

export default function DailyChallengeGame({ onBack }: DailyChallengeGameProps) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [challenge, setChallenge] = useState<DailyChallengeData | null>(null);
  const [response, setResponse] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [answerResult, setAnswerResult] = useState<DailyAnswerResult | null>(null);
  const [finalResult, setFinalResult] = useState<DailyFinalResult | null>(null);
  const [wagerInput, setWagerInput] = useState('0');
  const [hasStarted, setHasStarted] = useState(false);
  const [shareStatus, setShareStatus] = useState('');
  const startButtonRef = useRef<HTMLButtonElement>(null);
  const clueInputRef = useRef<HTMLInputElement>(null);
  const wagerInputRef = useRef<HTMLInputElement>(null);
  const finalInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError('');
      try {
        const data = await fetchDailyChallenge();
        setChallenge(data);
        setWagerInput('0');
      } catch {
        setError('Failed to load daily challenge.');
      } finally {
        setLoading(false);
      }
    };

    load();
  }, []);

  const step = useMemo(() => {
    if (!challenge) return { stage: 'done' as Stage, index: 0 };
    return nextStep(challenge);
  }, [challenge]);

  const singleDone = challenge ? challenge.progress.answers.single.filter(Boolean).length : 0;
  const doubleDone = challenge ? challenge.progress.answers.double.filter(Boolean).length : 0;
  const finalDone = challenge?.progress.final.submitted ? 1 : 0;
  const completedCount = singleDone + doubleDone + finalDone;
  const hasAnyProgress = completedCount > 0;

  useEffect(() => {
    if (hasAnyProgress) {
      setHasStarted(true);
    }
  }, [hasAnyProgress]);

  useEffect(() => {
    if (!challenge) return;
    if (step.stage === 'final' && !finalResult && challenge.progress.final.wager === null) {
      const max = challenge.progress.current_score >= 0 ? challenge.progress.current_score : 0;
      setWagerInput(String(Math.max(0, Math.min(max, Math.abs(challenge.progress.current_score)))));
    }
  }, [challenge, step.stage, finalResult]);

  useEffect(() => {
    if (!challenge) return;

    if (!hasStarted && !hasAnyProgress) {
      startButtonRef.current?.focus();
      return;
    }

    if (!answerResult && !finalResult && (step.stage === 'single' || step.stage === 'double')) {
      clueInputRef.current?.focus();
      return;
    }

    if (!answerResult && step.stage === 'final' && challenge.progress.final.wager === null) {
      wagerInputRef.current?.focus();
      return;
    }

    if (!answerResult && !finalResult && step.stage === 'final' && challenge.progress.final.wager !== null) {
      finalInputRef.current?.focus();
    }
  }, [challenge, hasStarted, hasAnyProgress, step.stage, answerResult, finalResult]);

  useEffect(() => {
    const onGlobalEnter = (e: KeyboardEvent) => {
      if (e.key !== 'Enter' || submitting || !challenge) return;
      const target = e.target as HTMLElement | null;
      if (!target) return;
      const tag = target.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || target.isContentEditable) return;

      if (!hasStarted && !hasAnyProgress) {
        e.preventDefault();
        setHasStarted(true);
        return;
      }

      if (answerResult) {
        e.preventDefault();
        setAnswerResult(null);
        setResponse('');
        return;
      }

      if (finalResult) {
        e.preventDefault();
        setFinalResult(null);
        setResponse('');
      }
    };

    window.addEventListener('keydown', onGlobalEnter);
    return () => window.removeEventListener('keydown', onGlobalEnter);
  }, [challenge, submitting, hasStarted, hasAnyProgress, answerResult, finalResult]);

  const clue = useMemo(() => {
    if (!challenge) return null;
    if (!answerResult) {
      if (step.stage === 'single') {
        return {
          category: challenge.single_category.name,
          clue: challenge.single_category.clues[step.index],
          stage: 'single' as const,
          index: step.index,
        };
      }
      if (step.stage === 'double') {
        return {
          category: challenge.double_category.name,
          clue: challenge.double_category.clues[step.index],
          stage: 'double' as const,
          index: step.index,
        };
      }
      return null;
    }

    if (answerResult.stage === 'single') {
      return {
        category: challenge.single_category.name,
        clue: challenge.single_category.clues[answerResult.index],
        stage: 'single' as const,
        index: answerResult.index,
      };
    }

    return {
      category: challenge.double_category.name,
      clue: challenge.double_category.clues[answerResult.index],
      stage: 'double' as const,
      index: answerResult.index,
    };
  }, [challenge, step, answerResult]);

  const applyAnswerToState = (result: DailyAnswerResult, submittedResponse: string) => {
    if (!challenge) return;
    const updated = structuredClone(challenge);
    const target = result.stage === 'single'
      ? updated.progress.answers.single
      : updated.progress.answers.double;

    const answer: DailyProgressAnswer = {
      clue_id: result.clue_id,
      attempt_id: result.attempt_id ?? undefined,
      response: submittedResponse,
      correct: result.correct,
      skipped: result.skipped ?? false,
      expected: result.expected,
      value: result.value,
      score_delta: result.score_delta,
    };
    target[result.index] = answer;
    updated.progress.current_score = result.score_after;
    setChallenge(updated);
  };

  const handleSubmitClue = async () => {
    if (!challenge || !clue || !response.trim()) return;
    setSubmitting(true);
    setError('');
    try {
      const result = await submitDailyAnswer(step.stage as 'single' | 'double', step.index, response, false);
      setAnswerResult(result);
      applyAnswerToState(result, response);
    } catch {
      setError('Failed to submit answer.');
    } finally {
      setSubmitting(false);
    }
  };

  const handleSkipClue = async () => {
    if (!challenge || !clue) return;
    setSubmitting(true);
    setError('');
    try {
      const result = await submitDailyAnswer(step.stage as 'single' | 'double', step.index, '', true);
      setAnswerResult(result);
      applyAnswerToState(result, '');
    } catch {
      setError('Failed to skip clue.');
    } finally {
      setSubmitting(false);
    }
  };

  const handleLockFinalWager = async () => {
    if (!challenge) return;

    const wager = Number.parseInt(wagerInput, 10);
    const maxWager = challenge.progress.current_score >= 0 ? challenge.progress.current_score : 0;
    if (Number.isNaN(wager) || wager < 0 || wager > maxWager) {
      setError(`Wager must be between 0 and ${maxWager}.`);
      return;
    }

    setSubmitting(true);
    setError('');
    try {
      await submitDailyFinalWager(wager);
      const refreshed = await fetchDailyChallenge();
      setChallenge(refreshed);
      setWagerInput(String(wager));
    } catch {
      setError('Failed to lock final wager.');
    } finally {
      setSubmitting(false);
    }
  };

  const handleSubmitFinal = async () => {
    if (!challenge || !response.trim()) return;

    if (challenge.progress.final.wager === null) {
      setError('Lock your wager before submitting Final Jeopardy.');
      return;
    }

    setSubmitting(true);
    setError('');
    try {
      const result = await submitDailyFinal(response);
      setFinalResult(result);
      const updated = structuredClone(challenge);
      updated.progress.final = {
        submitted: true,
        attempt_id: result.attempt_id,
        wager: challenge.progress.final.wager,
        response,
        correct: result.correct,
        expected: result.expected,
        score_delta: result.score_delta,
        completed_at: new Date().toISOString(),
      };
      updated.progress.current_score = result.final_score;
      setChallenge(updated);
    } catch {
      setError('Failed to submit final clue.');
    } finally {
      setSubmitting(false);
    }
  };

  const formatScore = (score: number): string => {
    const abs = Math.abs(score).toLocaleString();
    return score < 0 ? `-$${abs}` : `$${abs}`;
  };

  const buildShareText = (data: DailyChallengeData): string => {
    const scoreText = formatScore(data.progress.current_score);
    const dateText = formatChallengeDate(data.challenge_date);
    const shareUrl = window.location.origin;
    return `I scored ${scoreText} on Jeopardy Daily Challenge (${dateText}).\nPlay today's challenge: ${shareUrl}`;
  };

  const handleShare = async () => {
    if (!challenge) return;
    const text = buildShareText(challenge);
    setShareStatus('');
    try {
      if (navigator.share) {
        await navigator.share({
          title: 'Jeopardy Daily Challenge',
          text,
        });
        setShareStatus('Shared.');
        return;
      }
      await navigator.clipboard.writeText(text);
      setShareStatus('Copied to clipboard.');
    } catch {
      setShareStatus('Unable to share right now.');
    }
  };

  const handleClueInputKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key !== 'Enter' || submitting || !clue || answerResult) return;
    if (response.trim()) {
      void handleSubmitClue();
      return;
    }
    void handleSkipClue();
  };

  const handleFinalInputKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key !== 'Enter' || submitting || !challenge || finalResult) return;
    if (challenge.progress.final.wager === null) return;
    if (!response.trim()) return;
    void handleSubmitFinal();
  };

  const handleWagerInputKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key !== 'Enter' || submitting || !challenge || finalResult) return;
    if (challenge.progress.final.wager !== null) return;
    void handleLockFinalWager();
  };

  if (loading) {
    return (
      <div className="start-screen">
        <h1 className="title">JEOPARDY!</h1>
        <div className="loading">Loading daily challenge...</div>
      </div>
    );
  }

  if (error && !challenge) {
    return (
      <div className="start-screen">
        <h1 className="title">JEOPARDY!</h1>
        <div className="daily-error">{error}</div>
        <button className="round-btn" onClick={onBack}>Back</button>
      </div>
    );
  }

  if (!challenge) return null;

  const maxWager = challenge.progress.current_score >= 0 ? challenge.progress.current_score : 0;

  return (
    <div className="daily-screen">
      <div className="top-bar">
        <button className="new-game-btn" onClick={onBack}>Home</button>
        <Scoreboard score={challenge.progress.current_score} />
      </div>

      <div className="daily-shell">
        <div className="daily-header">
          <h2>Daily Challenge - {formatChallengeDate(challenge.challenge_date)}</h2>
        </div>

        <div className="daily-dots-shell">
          <div className="daily-dots-sections">
            <div className="daily-dot-group">
              <span className="daily-dot-label">Single</span>
              <div className="daily-dot-row">
                {Array.from({ length: 5 }).map((_, idx) => (
                  <span key={`s-${idx}`} className={`daily-dot ${idx < singleDone ? 'done' : ''}`} />
                ))}
              </div>
            </div>
            <div className="daily-dot-group">
              <span className="daily-dot-label">Double</span>
              <div className="daily-dot-row">
                {Array.from({ length: 5 }).map((_, idx) => (
                  <span key={`d-${idx}`} className={`daily-dot ${idx < doubleDone ? 'done' : ''}`} />
                ))}
              </div>
            </div>
            <div className="daily-dot-group final">
              <span className="daily-dot-label">Final</span>
              <div className="daily-dot-row">
                <span className={`daily-dot final ${finalDone === 1 ? 'done' : ''}`} />
              </div>
            </div>
          </div>
        </div>

        {!hasStarted && !hasAnyProgress && (
          <div className="daily-card daily-brief">
            <div className="clue-category">Today's Categories</div>
            <div className="daily-category-chip">Single Jeopardy: {challenge.single_category.name}</div>
            <div className="daily-category-chip">Double Jeopardy: {challenge.double_category.name}</div>
            <div className="daily-category-chip muted">Final Category: {challenge.final_clue.category}</div>
            <button ref={startButtonRef} className="submit-btn" onClick={() => setHasStarted(true)}>Start Daily Challenge</button>
          </div>
        )}

        {hasStarted && (step.stage === 'single' || step.stage === 'double' || answerResult) && clue && (
          <div className="daily-card">
            <div className="clue-category">
              {clue.stage === 'single' ? 'Single Jeopardy' : 'Double Jeopardy'} - {clue.category}
            </div>
            <div className="daily-value">${clue.clue.value.toLocaleString()}</div>
            <div className="clue-air-date">Aired on: {formatAirDate(clue.clue.air_date)}</div>
            <div className="clue-text">{clue.clue.clue_text}</div>

            {answerResult ? (
              <div className={`daily-result ${answerResult.correct ? 'is-correct' : 'is-incorrect'}`}>
                <div className={`result-banner ${answerResult.correct ? 'correct' : answerResult.skipped ? 'skipped' : 'incorrect'}`}>
                  {answerResult.correct ? 'CORRECT' : answerResult.skipped ? 'SKIPPED' : 'INCORRECT'}
                </div>
                <div className="expected">Correct response: {answerResult.expected}</div>
                <div className="result-value">
                  {answerResult.score_delta > 0 ? '+' : ''}${answerResult.score_delta.toLocaleString()}
                </div>
                <button
                  className="submit-btn"
                  onClick={() => {
                    setAnswerResult(null);
                    setResponse('');
                  }}
                >
                  Next Clue
                </button>
              </div>
            ) : (
              <>
                <input
                  ref={clueInputRef}
                  className="response-input"
                  placeholder="What is..."
                  value={response}
                  onChange={(e) => setResponse(e.target.value)}
                  onKeyDown={handleClueInputKeyDown}
                  disabled={submitting}
                />
                <div className="daily-answer-actions">
                  <button className="submit-btn" onClick={handleSubmitClue} disabled={submitting || !response.trim()}>
                    {submitting ? 'Submitting...' : 'Submit Answer'}
                  </button>
                  <button className="skip-btn" onClick={handleSkipClue} disabled={submitting}>
                    Skip
                  </button>
                </div>
              </>
            )}
          </div>
        )}

        {hasStarted && !answerResult && (finalResult || step.stage === 'final') && (
          <div className="daily-card">
            <div className="dd-banner">FINAL JEOPARDY</div>
            <div className="clue-category">The category is: {challenge.final_clue.category}</div>
            <div className="clue-air-date">Aired on: {formatAirDate(challenge.final_clue.air_date)}</div>
            {challenge.progress.final.wager === null ? (
              <>
                <div className="wager-prompt">Enter wager (0 - ${maxWager.toLocaleString()})</div>
                <input
                  ref={wagerInputRef}
                  type="number"
                  className="wager-input"
                  min={0}
                  max={maxWager}
                  value={wagerInput}
                  onChange={(e) => setWagerInput(e.target.value)}
                  onKeyDown={handleWagerInputKeyDown}
                  disabled={submitting || Boolean(finalResult)}
                />
                <button className="submit-btn" onClick={handleLockFinalWager} disabled={submitting}>
                  {submitting ? 'Locking...' : 'Lock Wager'}
                </button>
              </>
            ) : (
              <div className="wager-prompt">Wager Locked: ${challenge.progress.final.wager.toLocaleString()}</div>
            )}

            {challenge.progress.final.wager !== null && challenge.final_clue.clue_text && (
              <div className="clue-text">{challenge.final_clue.clue_text}</div>
            )}

            {finalResult ? (
              <div className={`daily-result ${finalResult.correct ? 'is-correct' : 'is-incorrect'}`}>
                <div className={`result-banner ${finalResult.correct ? 'correct' : 'incorrect'}`}>
                  {finalResult.correct ? 'CORRECT' : 'INCORRECT'}
                </div>
                <div className="expected">Correct response: {finalResult.expected}</div>
                <div className="result-value">
                  {finalResult.score_delta >= 0 ? '+' : ''}${finalResult.score_delta.toLocaleString()}
                </div>
                <button
                  className="submit-btn"
                  onClick={() => {
                    setFinalResult(null);
                    setResponse('');
                  }}
                >
                  View Final Score
                </button>
              </div>
            ) : challenge.progress.final.wager !== null ? (
              <>
                <input
                  ref={finalInputRef}
                  className="response-input"
                  placeholder="Who is / What is..."
                  value={response}
                  onChange={(e) => setResponse(e.target.value)}
                  onKeyDown={handleFinalInputKeyDown}
                  disabled={submitting}
                />
                <button className="submit-btn" onClick={handleSubmitFinal} disabled={submitting || !response.trim()}>
                  {submitting ? 'Submitting...' : 'Submit Final'}
                </button>
              </>
            ) : null}
          </div>
        )}

        {hasStarted && step.stage === 'done' && !finalResult && (
          <div className="daily-card">
            <div className="result-banner correct">Challenge Complete</div>
            <div className="game-over-text">
              Final Score: {challenge.progress.current_score < 0 ? '-' : ''}${Math.abs(challenge.progress.current_score).toLocaleString()}
            </div>
            <button className="submit-btn" onClick={handleShare}>Share Result</button>
            {shareStatus && <div className="share-status">{shareStatus}</div>}
          </div>
        )}

        {error && <div className="daily-error">{error}</div>}
      </div>
    </div>
  );
}
