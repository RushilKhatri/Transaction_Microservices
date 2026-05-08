/**
 * src/components/TransactionFeed.jsx
 * Right panel: scrollable feed of the 20 most recent transactions.
 * New rows flash yellow on first appearance.
 */
import { useRef, useEffect, useState } from 'react';

const INR = (v) =>
    v.toLocaleString('en-IN', { style: 'currency', currency: 'INR' });

function relativeTime(isoString) {
    const diff = Math.floor((Date.now() - new Date(isoString)) / 1000);
    if (diff < 5) return 'just now';
    if (diff < 60) return `${diff}s ago`;
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return `${Math.floor(diff / 86400)}d ago`;
}

export default function TransactionFeed({ transactions, error }) {
    const prevIdsRef = useRef(new Set());
    const [newIds, setNewIds] = useState(new Set());

    useEffect(() => {
        const currentIds = new Set(transactions.map((t) => t.id));
        const fresh = new Set(
            [...currentIds].filter((id) => !prevIdsRef.current.has(id))
        );
        if (fresh.size > 0) {
            setNewIds(fresh);
            // Animation lasts 1.5s — clear after
            const timer = setTimeout(() => setNewIds(new Set()), 1600);
            prevIdsRef.current = currentIds;
            return () => clearTimeout(timer);
        }
        prevIdsRef.current = currentIds;
    }, [transactions]);

    return (
        <div className="card feed-card">
            <h2 className="card-title">Transaction Feed</h2>
            {error && <p className="inline-error">⚠ {error}</p>}
            <div className="feed-scroll">
                {transactions.length === 0 ? (
                    <p className="feed-empty">No transactions yet.</p>
                ) : (
                    <ul className="feed-list">
                        {transactions.map((tx) => (
                            <li
                                key={tx.id}
                                className={[
                                    'feed-row',
                                    tx.fraud_flagged ? 'feed-row--flagged' : 'feed-row--clean',
                                    newIds.has(tx.id) ? 'feed-row--new' : '',
                                ]
                                    .filter(Boolean)
                                    .join(' ')}
                            >
                                <div className="feed-row-main">
                                    <span className="feed-route">
                                        {tx.from_name} → {tx.to_name}
                                    </span>
                                    <span className="feed-amount">{INR(tx.amount)}</span>
                                    <span
                                        className={`feed-badge ${tx.fraud_flagged ? 'badge--flagged' : 'badge--clear'
                                            }`}
                                    >
                                        {tx.fraud_flagged ? 'FLAGGED' : 'CLEAR'}
                                    </span>
                                </div>
                                {tx.fraud_flagged && (
                                    <div className="feed-row-sub">
                                        {tx.rules_triggered && (
                                            <span>Rules: {tx.rules_triggered} · </span>
                                        )}
                                        <span>Score: {(tx.fraud_score * 100).toFixed(0)}%</span>
                                    </div>
                                )}
                                <div className="feed-row-time">{relativeTime(tx.created_at)}</div>
                            </li>
                        ))}
                    </ul>
                )}
            </div>
        </div>
    );
}
