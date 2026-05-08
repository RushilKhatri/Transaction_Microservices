/**
 * src/components/AccountBalances.jsx
 * Full-width grid of all 10 accounts with animated balance bars.
 */

const INR = (v) =>
    v.toLocaleString('en-IN', { style: 'currency', currency: 'INR' });

export default function AccountBalances({ accounts, error }) {
    const maxBalance = Math.max(...accounts.map((a) => a.balance || 0), 1);

    return (
        <div className="card balances-card">
            <h2 className="card-title">Account Balances</h2>
            {error && <p className="inline-error">⚠ {error}</p>}
            <div className="balances-grid">
                {accounts.map((acc) => {
                    const pct = ((acc.balance / maxBalance) * 100).toFixed(1);
                    return (
                        <div
                            key={acc.id}
                            className={`account-card ${acc.isHighRisk ? 'account-card--high-risk' : ''}`}
                        >
                            {acc.isHighRisk && (
                                <span className="high-risk-badge">HIGH RISK</span>
                            )}
                            <div className="account-name">{acc.owner_name}</div>
                            <div className="account-balance">{INR(acc.balance)}</div>
                            <div className="balance-bar-track">
                                <div
                                    className="balance-bar-fill"
                                    style={{ width: `${pct}%` }}
                                    aria-label={`Balance ${pct}% of max`}
                                />
                            </div>
                        </div>
                    );
                })}
            </div>
        </div>
    );
}
