import { useState } from 'react';
import type { BoardData } from '../types';
import { fetchBoard } from '../api';
import Board from './Board';
import ClueModal from './ClueModal';
import Scoreboard from './Scoreboard';

type Screen = 'start' | 'loading' | 'board';

const ROUND_MAX = { 1: 1000, 2: 2000 };

interface ClassicGameProps {
  onBack: () => void;
}

export default function ClassicGame({ onBack }: ClassicGameProps) {
  const [screen, setScreen] = useState<Screen>('start');
  const [board, setBoard] = useState<BoardData | null>(null);
  const [score, setScore] = useState(0);
  const [answeredClues, setAnsweredClues] = useState<Set<number>>(new Set());
  const [activeClue, setActiveClue] = useState<{
    id: number;
    value: number;
    isDailyDouble: boolean;
  } | null>(null);

  const startGame = async (round: number) => {
    setScreen('loading');
    try {
      const b = await fetchBoard(round);
      setBoard(b);
      setScore(0);
      setAnsweredClues(new Set());
      setScreen('board');
    } catch {
      setScreen('start');
    }
  };

  const handleClueClick = (id: number, value: number, isDailyDouble: boolean) => {
    setActiveClue({ id, value, isDailyDouble });
  };

  const handleClueClose = (result: { correct: boolean; value: number } | null) => {
    if (result && activeClue) {
      setScore((s) => s + (result.correct ? result.value : -result.value));
      setAnsweredClues((prev) => new Set(prev).add(activeClue.id));
    }
    setActiveClue(null);
  };

  const allAnswered = board
    ? board.categories.every((cat) => cat.clues.every((c) => answeredClues.has(c.id)))
    : false;

  if (screen === 'start') {
    return (
      <div className="start-screen">
        <h1 className="title">JEOPARDY!</h1>
        <div className="round-buttons">
          <button onClick={() => startGame(1)} className="round-btn">Single Jeopardy</button>
          <button onClick={() => startGame(2)} className="round-btn">Double Jeopardy</button>
        </div>
        <button className="new-game-btn" onClick={onBack}>Back</button>
      </div>
    );
  }

  if (screen === 'loading') {
    return (
      <div className="start-screen">
        <h1 className="title">JEOPARDY!</h1>
        <div className="loading">Generating board...</div>
        <button className="new-game-btn" onClick={onBack}>Back</button>
      </div>
    );
  }

  return (
    <div className="game-screen">
      <div className="top-bar">
        <button className="new-game-btn" onClick={onBack}>Home</button>
        <Scoreboard score={score} />
      </div>
      {board && (
        <Board
          board={board}
          answeredClues={answeredClues}
          onClueClick={handleClueClick}
        />
      )}
      {allAnswered && (
        <div className="game-over">
          <div className="game-over-text">
            Final Score: {score < 0 ? '-' : ''}${Math.abs(score).toLocaleString()}
          </div>
          <button className="round-btn" onClick={() => setScreen('start')}>Play Again</button>
        </div>
      )}
      {activeClue && board && (
        <ClueModal
          clueId={activeClue.id}
          value={activeClue.value}
          isDailyDouble={activeClue.isDailyDouble}
          currentScore={score}
          roundMax={ROUND_MAX[board.round as 1 | 2]}
          onClose={handleClueClose}
        />
      )}
    </div>
  );
}
