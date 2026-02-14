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
