interface Props {
  score: number;
}

export default function Scoreboard({ score }: Props) {
  return (
    <div className="scoreboard">
      <span className="score-label">Score</span>
      <span className={`score-value ${score < 0 ? 'negative' : ''}`}>
        {score < 0 ? '-' : ''}${Math.abs(score).toLocaleString()}
      </span>
    </div>
  );
}
