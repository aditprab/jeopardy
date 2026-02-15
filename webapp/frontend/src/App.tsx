import { useState } from 'react';
import ClassicGame from './components/ClassicGame';
import DailyChallengeGame from './components/DailyChallengeGame';

type Mode = 'landing' | 'daily' | 'classic';

function FooterCredit() {
  return (
    <footer className="app-footer">
      <span>Made with ❤️</span>
      <span className="app-footer-by">by Adithya Prabhakaran</span>
    </footer>
  );
}

function Landing({ onSelect }: { onSelect: (mode: Exclude<Mode, 'landing'>) => void }) {
  return (
    <div className="landing-screen">
      <h1 className="title">JEOPARDY!</h1>
      <div className="mode-grid">
        <button className="mode-card" onClick={() => onSelect('daily')}>
          <span className="mode-title">Daily Challenge</span>
          <span className="mode-description">One challenge each day: Single, Double, then Final.</span>
        </button>
      </div>
    </div>
  );
}

export default function App() {
  const [mode, setMode] = useState<Mode>('landing');

  return (
    <>
      {mode === 'landing' && <Landing onSelect={(nextMode) => setMode(nextMode)} />}
      {mode === 'daily' && <DailyChallengeGame onBack={() => setMode('landing')} />}
      {mode === 'classic' && <ClassicGame onBack={() => setMode('landing')} />}
      <FooterCredit />
    </>
  );
}
