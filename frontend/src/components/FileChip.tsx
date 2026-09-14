import styles from "./FileChip.module.css";

type Props = {
  name: string;
  onRemove?: () => void;
};

export default function FileChip({ name, onRemove }: Props) {
  return (
    <div className={styles.chip}>
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
        <polyline points="14 2 14 8 20 8"/>
      </svg>
      <span className={styles.name} title={name}>{name}</span>
      {onRemove && (
        <button className={styles.remove} onClick={onRemove} aria-label={`Remove ${name}`} type="button">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
            <line x1="18" y1="6" x2="6" y2="18"/>
            <line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </button>
      )}
    </div>
  );
}
