import type { BoardData } from '../types';
import CategoryHeader from './CategoryHeader';
import ClueCell from './ClueCell';

interface Props {
  board: BoardData;
  answeredClues: Set<number>;
  onClueClick: (clueId: number, value: number, isDailyDouble: boolean) => void;
}

export default function Board({ board, answeredClues, onClueClick }: Props) {
  return (
    <div className="board">
      {/* Category headers row */}
      <div className="board-row headers">
        {board.categories.map((cat) => (
          <CategoryHeader key={cat.name} name={cat.name} />
        ))}
      </div>
      {/* Clue rows: 5 rows of values */}
      {[0, 1, 2, 3, 4].map((rowIdx) => (
        <div className="board-row" key={rowIdx}>
          {board.categories.map((cat) => {
            const clue = cat.clues[rowIdx];
            return (
              <ClueCell
                key={clue.id}
                value={clue.value}
                answered={answeredClues.has(clue.id)}
                onClick={() => onClueClick(clue.id, clue.value, clue.is_daily_double)}
              />
            );
          })}
        </div>
      ))}
    </div>
  );
}
