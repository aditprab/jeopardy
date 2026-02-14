interface Props {
  value: number;
  answered: boolean;
  onClick: () => void;
}

export default function ClueCell({ value, answered, onClick }: Props) {
  return (
    <button
      className={`clue-cell ${answered ? 'answered' : ''}`}
      onClick={onClick}
      disabled={answered}
    >
      {answered ? '' : `$${value}`}
    </button>
  );
}
