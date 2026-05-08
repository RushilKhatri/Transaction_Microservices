/**
 * src/components/FraudAlertBanner.jsx
 * Full-width red banner listing all active alerts with dismiss buttons.
 * Only renders when there are active alerts.
 */
export default function FraudAlertBanner({ activeAlerts, dismissAlert, accounts }) {
    if (!activeAlerts || activeAlerts.length === 0) return null;

    const accountName = (id) => {
        const acc = accounts?.find((a) => a.id === id);
        return acc ? acc.owner_name : id?.slice(0, 8) + '…';
    };

    return (
        <div className="fraud-banner" role="alert">
            <div className="fraud-banner-header">
                <span className="fraud-banner-icon">⚠️</span>
                <strong>Active Fraud Alerts ({activeAlerts.length})</strong>
            </div>
            <ul className="fraud-banner-list">
                {activeAlerts.map((alert, idx) => (
                    <li key={alert.id} className="fraud-banner-row">
                        <span className="fraud-banner-text">
                            <strong>Alert #{idx + 1}</strong>
                            {' — Account: '}
                            <strong>{accountName(alert.account_id)}</strong>
                            {` — Score: ${(alert.fraud_score * 100).toFixed(0)}%`}
                            {alert.rules_triggered
                                ? ` — Rules: ${alert.rules_triggered}`
                                : ''}
                        </span>
                        <button
                            className="btn-dismiss"
                            onClick={() => dismissAlert(alert.id)}
                            aria-label={`Dismiss alert ${idx + 1}`}
                        >
                            Dismiss
                        </button>
                    </li>
                ))}
            </ul>
        </div>
    );
}
