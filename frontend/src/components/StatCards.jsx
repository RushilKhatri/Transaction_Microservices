/**
 * src/components/StatCards.jsx
 * Four metric cards: Total Transactions, Fraud Flagged, Total Volume, Active Alerts
 */
import { useMemo } from 'react';

function formatVolume(total) {
    if (total >= 1_00_00_000) {
        return `₹${(total / 1_00_00_000).toFixed(2)} Cr`;
    }
    if (total >= 1_00_000) {
        return `₹${(total / 1_00_000).toFixed(2)} L`;
    }
    return total.toLocaleString('en-IN', { style: 'currency', currency: 'INR' });
}

export default function StatCards({ transactions, activeAlerts }) {
    const stats = useMemo(() => {
        const total = transactions.length;
        const fraudCount = transactions.filter((t) => t.fraud_flagged).length;
        const volume = transactions.reduce((sum, t) => sum + (t.amount || 0), 0);
        return { total, fraudCount, volume };
    }, [transactions]);

    const alertCount = activeAlerts.length;
    const alertClass =
        alertCount > 5 ? 'stat-value danger' : alertCount > 0 ? 'stat-value warning' : 'stat-value';

    return (
        <div className="stat-cards-row">
            <div className="stat-card">
                <span className="stat-label">Total Transactions</span>
                <span className="stat-value">{stats.total.toLocaleString('en-IN')}</span>
            </div>
            <div className="stat-card">
                <span className="stat-label">Fraud Flagged</span>
                <span className={stats.fraudCount > 0 ? 'stat-value danger' : 'stat-value'}>
                    {stats.fraudCount.toLocaleString('en-IN')}
                </span>
            </div>
            <div className="stat-card">
                <span className="stat-label">Total Volume</span>
                <span className="stat-value">{formatVolume(stats.volume)}</span>
            </div>
            <div className="stat-card">
                <span className="stat-label">Active Alerts</span>
                <span className={alertClass}>{alertCount}</span>
            </div>
        </div>
    );
}
