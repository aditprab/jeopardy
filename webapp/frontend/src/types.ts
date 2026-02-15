export interface Clue {
  id: number;
  value: number;
  is_daily_double: boolean;
}

export interface Category {
  name: string;
  clues: Clue[];
}

export interface BoardData {
  round: number;
  categories: Category[];
}

export interface ClueDetail {
  id: number;
  category: string;
  value: number;
  clue_text: string;
  expected_response: string;
  air_date: string;
}

export interface AnswerResult {
  correct: boolean;
  expected: string;
  attempt_id?: number;
}

export interface AppealResult {
  appeal_id: number;
  final_correct: boolean;
  overturn: boolean;
  reason_code: string;
  reason: string;
  confidence: number;
  expected: string;
  trace_id: string;
  status: 'decided';
}

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
  clue_text: string;
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

export interface DailyAppealApplyResult {
  stage: 'single' | 'double' | 'final';
  index: number | null;
  attempt_id: number;
  overturn: boolean;
  final_correct: boolean;
  reason_code: string;
  reason: string;
  confidence: number;
  score_after: number;
  score_delta_adjustment: number;
}
