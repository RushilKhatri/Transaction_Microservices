/**
 * src/components/ServiceStatus.jsx
 * Three coloured dots showing health of all three microservices.
 * Polls /health every 5 seconds independently.
 */
import { useState, useEffect } from 'react';
import { checkHealth, TRANSACTION_URL, FRAUD_URL, NOTIFICATION_URL } from '../api/client';

const SERVICES = [
    { label: 'Transaction', url: TRANSACTION_URL },
    { label: 'Fraud', url: FRAUD_URL },
    { label: 'Notification', url: NOTIFICATION_URL },
];

const POLL_MS = 5000;

export default function ServiceStatus() {
    const [statuses, setStatuses] = useState({ Transaction: null, Fraud: null, Notification: null });

    useEffect(() => {
        const poll = async () => {
            const results = await Promise.allSettled(
                SERVICES.map((s) => checkHealth(s.url))
            );
            const next = {};
            SERVICES.forEach((s, i) => {
                next[s.label] =
                    results[i].status === 'fulfilled' ? results[i].value : false;
            });
            setStatuses(next);
        };

        poll();
        const id = setInterval(poll, POLL_MS);
        return () => clearInterval(id);
    }, []);

    return (
        <div className="service-status">
            {SERVICES.map(({ label }) => (
                <div key={label} className="service-status-item">
                    <span
                        className={`status-dot ${statuses[label] === null
                                ? 'dot-unknown'
                                : statuses[label]
                                    ? 'dot-green'
                                    : 'dot-red'
                            }`}
                        aria-label={`${label} service ${statuses[label] ? 'healthy' : 'down'}`}
                    />
                    <span className="status-label">{label} service</span>
                </div>
            ))}
        </div>
    );
}
