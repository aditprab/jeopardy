import type { BoardData, ClueDetail, AnswerResult, AppealResult } from './types';

export async function fetchBoard(round: number): Promise<BoardData> {
  const res = await fetch(`/api/board?round=${round}`);
  if (!res.ok) throw new Error('Failed to fetch board');
  return res.json();
}

export async function fetchClue(id: number): Promise<ClueDetail> {
  const res = await fetch(`/api/clue/${id}`);
  if (!res.ok) throw new Error('Failed to fetch clue');
  return res.json();
}

export async function submitAnswer(clueId: number, response: string): Promise<AnswerResult> {
  const res = await fetch('/api/answer', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ clue_id: clueId, response }),
  });
  if (!res.ok) throw new Error('Failed to submit answer');
  return res.json();
}

export async function submitAppeal(
  attemptId: number,
  userJustification?: string,
): Promise<AppealResult> {
  const res = await fetch('/api/appeal', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      attempt_id: attemptId,
      user_justification: userJustification || null,
    }),
  });
  if (!res.ok) throw new Error('Failed to submit appeal');
  return res.json();
}
