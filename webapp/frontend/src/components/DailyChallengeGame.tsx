import { useEffect, useMemo, useState } from 'react';
import {
  applyDailyAppeal,
  fetchDailyChallenge,
  submitAppeal,
  submitDailyAnswer,
  submitDailyFinal,
} from '../api';
import type {
  DailyChallengeData,
  DailyProgressAnswer,
  DailyAnswerResult,
  DailyFinalResult,
  AppealResult,
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
  const [appealText, setAppealText] = useState('');
  const [appealLoading, setAppealLoading] = useState(false);
  const [appealError, setAppealError] = useState('');
  const [appealResult, setAppealResult] = useState<AppealResult | null>(null);
  const [hasStarted, setHasStarted] = useState(false);

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
    if (step.stage === 'final' && !finalResult) {
      const max = challenge.progress.current_score >= 0 ? challenge.progress.current_score : 1000;
      setWagerInput(String(Math.max(0, Math.min(max, Math.abs(challenge.progress.current_score)))));
    }
  }, [challenge, step.stage, finalResult]);

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

  const clearAppealState = () => {
    setAppealText('');
    setAppealLoading(false);
    setAppealError('');
    setAppealResult(null);
  };

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
      clearAppealState();
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
      clearAppealState();
      applyAnswerToState(result, '');
    } catch {
      setError('Failed to skip clue.');
    } finally {
      setSubmitting(false);
    }
  };

  const handleSubmitFinal = async () => {
    if (!challenge || !response.trim()) return;

    const wager = Number.parseInt(wagerInput, 10);
    const maxWager = challenge.progress.current_score >= 0 ? challenge.progress.current_score : 1000;
    if (Number.isNaN(wager) || wager < 0 || wager > maxWager) {
      setError(`Wager must be between 0 and ${maxWager}.`);
      return;
    }

    setSubmitting(true);
    setError('');
    try {
      const result = await submitDailyFinal(wager, response);
      setFinalResult(result);
      clearAppealState();
      const updated = structuredClone(challenge);
      updated.progress.final = {
        submitted: true,
        attempt_id: result.attempt_id,
        wager: result.wager,
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

  const handleAppeal = async () => {
    if (!challenge || appealLoading) return;

    let stage: 'single' | 'double' | 'final';
    let index: number | undefined;
    let attemptId: number | null = null;

    if (answerResult) {
      stage = answerResult.stage;
      index = answerResult.index;
      attemptId = answerResult.attempt_id;
    } else if (finalResult) {
      stage = 'final';
      attemptId = finalResult.attempt_id;
    } else {
      return;
    }

    if (!attemptId) return;

    setAppealLoading(true);
    setAppealError('');
    try {
      const appealed = await submitAppeal(attemptId, appealText.trim() || undefined);
      setAppealResult(appealed);
      const applied = await applyDailyAppeal(stage, attemptId, index);
      const updated = structuredClone(challenge);
      updated.progress.current_score = applied.score_after;

      if (stage === 'final') {
        if (updated.progress.final.submitted) {
          updated.progress.final.correct = applied.final_correct;
          if (updated.progress.final.wager !== null) {
            updated.progress.final.score_delta = applied.final_correct
              ? updated.progress.final.wager
              : -updated.progress.final.wager;
          }
        }
        if (finalResult) {
          setFinalResult({
            ...finalResult,
            correct: applied.final_correct,
            score_delta: updated.progress.final.score_delta ?? finalResult.score_delta,
            final_score: applied.score_after,
          });
        }
      } else if (index !== undefined) {
        const target = stage === 'single'
          ? updated.progress.answers.single
          : updated.progress.answers.double;
        const existing = target[index];
        if (existing) {
          existing.correct = applied.final_correct;
          existing.score_delta = applied.final_correct ? existing.value : -existing.value;
        }
        if (answerResult) {
          setAnswerResult({
            ...answerResult,
            correct: applied.final_correct,
            score_delta: existing ? existing.score_delta : answerResult.score_delta,
            score_after: applied.score_after,
          });
        }
      }

      setChallenge(updated);
    } catch {
      setAppealError('Appeal failed. Please try again.');
    } finally {
      setAppealLoading(false);
    }
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

  const maxWager = challenge.progress.current_score >= 0 ? challenge.progress.current_score : 1000;

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
            <button className="submit-btn" onClick={() => setHasStarted(true)}>Start Daily Challenge</button>
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
                {!answerResult.correct && !answerResult.skipped && !appealResult && answerResult.attempt_id && (
                  <div className="appeal-block">
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
                  </div>
                )}
                {appealError && <div className="appeal-error">{appealError}</div>}
                {appealResult && (
                  <div className={`appeal-result ${appealResult.overturn ? 'overturned' : 'denied'}`}>
                    {appealResult.overturn ? 'Appeal Accepted' : 'Appeal Denied'}: {appealResult.reason}
                  </div>
                )}
                <button
                  className="submit-btn"
                  onClick={() => {
                    setAnswerResult(null);
                    setResponse('');
                    clearAppealState();
                  }}
                >
                  Next Clue
                </button>
              </div>
            ) : (
              <>
                <input
                  className="response-input"
                  placeholder="What is..."
                  value={response}
                  onChange={(e) => setResponse(e.target.value)}
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

        {hasStarted && (step.stage === 'final' || finalResult) && (
          <div className="daily-card">
            <div className="dd-banner">FINAL JEOPARDY</div>
            <div className="clue-category">{challenge.final_clue.category}</div>
            <div className="clue-air-date">Aired on: {formatAirDate(challenge.final_clue.air_date)}</div>
            <div className="wager-prompt">Enter wager (0 - ${maxWager.toLocaleString()})</div>
            <input
              type="number"
              className="wager-input"
              min={0}
              max={maxWager}
              value={wagerInput}
              onChange={(e) => setWagerInput(e.target.value)}
              disabled={submitting || Boolean(finalResult)}
            />
            <div className="clue-text">{challenge.final_clue.clue_text}</div>

            {finalResult ? (
              <div className={`daily-result ${finalResult.correct ? 'is-correct' : 'is-incorrect'}`}>
                <div className={`result-banner ${finalResult.correct ? 'correct' : 'incorrect'}`}>
                  {finalResult.correct ? 'CORRECT' : 'INCORRECT'}
                </div>
                <div className="expected">Correct response: {finalResult.expected}</div>
                <div className="result-value">
                  {finalResult.score_delta >= 0 ? '+' : ''}${finalResult.score_delta.toLocaleString()}
                </div>
                {!finalResult.correct && !appealResult && finalResult.attempt_id && (
                  <div className="appeal-block">
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
                  </div>
                )}
                {appealError && <div className="appeal-error">{appealError}</div>}
                {appealResult && (
                  <div className={`appeal-result ${appealResult.overturn ? 'overturned' : 'denied'}`}>
                    {appealResult.overturn ? 'Appeal Accepted' : 'Appeal Denied'}: {appealResult.reason}
                  </div>
                )}
                <button
                  className="submit-btn"
                  onClick={() => {
                    setFinalResult(null);
                    setResponse('');
                    clearAppealState();
                  }}
                >
                  View Final Score
                </button>
              </div>
            ) : (
              <>
                <input
                  className="response-input"
                  placeholder="Who is / What is..."
                  value={response}
                  onChange={(e) => setResponse(e.target.value)}
                  disabled={submitting}
                />
                <button className="submit-btn" onClick={handleSubmitFinal} disabled={submitting || !response.trim()}>
                  {submitting ? 'Submitting...' : 'Submit Final'}
                </button>
              </>
            )}
          </div>
        )}

        {hasStarted && step.stage === 'done' && !finalResult && (
          <div className="daily-card">
            <div className="result-banner correct">Challenge Complete</div>
            <div className="game-over-text">
              Final Score: {challenge.progress.current_score < 0 ? '-' : ''}${Math.abs(challenge.progress.current_score).toLocaleString()}
            </div>
            <button className="round-btn" onClick={onBack}>Back Home</button>
          </div>
        )}

        {error && <div className="daily-error">{error}</div>}
      </div>
    </div>
  );
}
