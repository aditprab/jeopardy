export interface DailyClue {
  id: number;
  value: number;
  clue_text: string;
  air_date: string;
}

export interface DailyCategory {
  name: string;
  clues: DailyClue[];
}

export interface DailyFinalClue {
  id: number;
  category: string;
  clue_text: string | null;
  air_date: string;
}

export interface DailyProgressAnswer {
  clue_id: number;
  attempt_id?: number;
  response: string;
  correct: boolean;
  skipped?: boolean;
  expected: string;
  value: number;
  score_delta: number;
}

export interface DailyFinalProgress {
  submitted: boolean;
  attempt_id: number | null;
  wager: number | null;
  response: string | null;
  correct: boolean | null;
  expected: string | null;
  score_delta: number | null;
  completed_at: string | null;
}

export interface DailyProgress {
  current_score: number;
  answers: {
    single: Array<DailyProgressAnswer | null>;
    double: Array<DailyProgressAnswer | null>;
  };
  final: DailyFinalProgress;
}

export interface DailyChallengeData {
  challenge_date: string;
  timezone: string;
  single_category: DailyCategory;
  double_category: DailyCategory;
  final_clue: DailyFinalClue;
  progress: DailyProgress;
}

export interface DailyAnswerResult {
  idempotent: boolean;
  stage: 'single' | 'double';
  index: number;
  clue_id: number;
  attempt_id: number | null;
  correct: boolean;
  skipped?: boolean;
  expected: string;
  value: number;
  score_delta: number;
  score_after: number;
}

export interface DailyFinalResult {
  idempotent: boolean;
  attempt_id: number | null;
  correct: boolean;
  expected: string;
  wager: number;
  score_delta: number;
  final_score: number;
}

export interface DailyFinalWagerResult {
  idempotent: boolean;
  wager: number | null;
}
