import type { DailyLeaderboardData } from '../types';

interface Props {
  leaderboard: DailyLeaderboardData | null;
}

function formatScore(score: number): string {
  return `${score < 0 ? '-' : ''}$${Math.abs(score).toLocaleString()}`;
}

export default function DailyLeaderboard({ leaderboard }: Props) {
  if (!leaderboard) {
    return (
      <aside className="leaderboard-card">
        <div className="leaderboard-header">
          <span className="leaderboard-title">Daily Leaderboard</span>
        </div>
        <div className="leaderboard-empty">Complete today&apos;s challenge to post a score.</div>
      </aside>
    );
  }

  const hasEntries = leaderboard.entries.length > 0;

  return (
    <aside className="leaderboard-card">
      <div className="leaderboard-header">
        <span className="leaderboard-title">Daily Leaderboard</span>
      </div>

      {hasEntries ? (
        <div className="leaderboard-list">
          {leaderboard.entries.map((entry) => (
            <div
              key={`${entry.rank}-${entry.player_name}-${entry.score}`}
              className={`leaderboard-row ${entry.is_current_player ? 'current-player' : ''}`}
            >
              <span className="leaderboard-rank">#{entry.rank}</span>
              <span className="leaderboard-name">{entry.player_name}</span>
              <span className="leaderboard-score">{formatScore(entry.score)}</span>
            </div>
          ))}
        </div>
      ) : (
        <div className="leaderboard-empty">No completed scores yet today.</div>
      )}

      {leaderboard.current_player_entry && !leaderboard.entries.some((entry) => entry.is_current_player) && (
        <div className="leaderboard-current">
          <span>Your rank</span>
          <strong>
            #{leaderboard.current_player_entry.rank} · {formatScore(leaderboard.current_player_entry.score)}
          </strong>
        </div>
      )}
    </aside>
  );
}
