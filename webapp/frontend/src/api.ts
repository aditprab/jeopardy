import type { BoardData, ClueDetail, AnswerResult, AppealResult } from './types';

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');

function apiUrl(path: string): string {
  return API_BASE_URL ? `${API_BASE_URL}${path}` : path;
}

export async function fetchBoard(round: number): Promise<BoardData> {
  const res = await fetch(apiUrl(`/api/board?round=${round}`));
  if (!res.ok) throw new Error('Failed to fetch board');
  return res.json();
}

export async function fetchClue(id: number): Promise<ClueDetail> {
  const res = await fetch(apiUrl(`/api/clue/${id}`));
  if (!res.ok) throw new Error('Failed to fetch clue');
  return res.json();
}

export async function submitAnswer(clueId: number, response: string): Promise<AnswerResult> {
  const res = await fetch(apiUrl('/api/answer'), {
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
  const res = await fetch(apiUrl('/api/appeal'), {
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
