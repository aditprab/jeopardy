import { useState } from 'react';
import DailyChallengeGame from './components/DailyChallengeGame';

type Mode = 'landing' | 'daily';

function FooterCredit() {
  return (
    <footer className="app-footer">
      <span>Made with ❤️</span>
      <span className="app-footer-by">by</span>
      <a
        className="app-footer-link"
        href="https://www.linkedin.com/in/adithyaprabhakaran/"
        target="_blank"
        rel="noopener noreferrer"
      >
        Adithya Prabhakaran
      </a>
    </footer>
  );
}

function Landing({ onSelect }: { onSelect: () => void }) {
  return (
    <div className="landing-screen">
      <h1 className="title">JEOPARDY!</h1>
      <div className="mode-grid">
        <button className="mode-card" onClick={onSelect}>
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
      {mode === 'landing' && <Landing onSelect={() => setMode('daily')} />}
      {mode === 'daily' && <DailyChallengeGame onBack={() => setMode('landing')} />}
      <FooterCredit />
    </>
  );
}
