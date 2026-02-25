import type {
  BoardData,
  ClueDetail,
  AnswerResult,
  DailyChallengeData,
  DailyAnswerResult,
  DailyFinalResult,
  DailyFinalWagerResult,
} from './types';

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
const PLAYER_TOKEN_KEY = 'jeopardy_player_token';

function apiUrl(path: string): string {
  return API_BASE_URL ? `${API_BASE_URL}${path}` : path;
}

function getPlayerToken(): string | null {
  return localStorage.getItem(PLAYER_TOKEN_KEY);
}

function updatePlayerToken(res: Response): void {
  const token = res.headers.get('X-Player-Token');
  if (token) {
    localStorage.setItem(PLAYER_TOKEN_KEY, token);
  }
}

function authHeaders(): Record<string, string> {
  const token = getPlayerToken();
  if (!token) return {};
  return { 'X-Player-Token': token };
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

export async function fetchDailyChallenge(): Promise<DailyChallengeData> {
  const res = await fetch(apiUrl('/api/daily-challenge'), {
    headers: authHeaders(),
  });
  updatePlayerToken(res);
  if (!res.ok) throw new Error('Failed to fetch daily challenge');
  return res.json();
}

export async function submitDailyAnswer(
  stage: 'single' | 'double',
  index: number,
  response: string,
  skipped = false,
): Promise<DailyAnswerResult> {
  const res = await fetch(apiUrl('/api/daily-challenge/answer'), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...authHeaders(),
    },
    body: JSON.stringify({ stage, index, response, skipped }),
  });
  updatePlayerToken(res);
  if (!res.ok) throw new Error('Failed to submit daily answer');
  return res.json();
}

export async function submitDailyFinalWager(
  wager: number,
): Promise<DailyFinalWagerResult> {
  const res = await fetch(apiUrl('/api/daily-challenge/final/wager'), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...authHeaders(),
    },
    body: JSON.stringify({ wager }),
  });
  updatePlayerToken(res);
  if (!res.ok) throw new Error('Failed to submit daily final wager');
  return res.json();
}

export async function submitDailyFinal(
  response: string,
): Promise<DailyFinalResult> {
  const res = await fetch(apiUrl('/api/daily-challenge/final'), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...authHeaders(),
    },
    body: JSON.stringify({ response }),
  });
  updatePlayerToken(res);
  if (!res.ok) throw new Error('Failed to submit daily final answer');
  return res.json();
}

export async function resetDailyChallenge(): Promise<{ reset: boolean; deleted_rows: number }> {
  const res = await fetch(apiUrl('/api/daily-challenge/reset'), {
    method: 'POST',
    headers: authHeaders(),
  });
  updatePlayerToken(res);
  if (!res.ok) throw new Error('Failed to reset daily challenge progress');
  return res.json();
}
