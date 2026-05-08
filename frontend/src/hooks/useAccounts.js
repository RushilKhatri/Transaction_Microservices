/**
 * src/hooks/useAccounts.js
 * Polls all 10 seeded accounts every 3 seconds.
 * Accepts activeAlerts to compute `isHighRisk` per account.
 */
import { useState, useEffect, useCallback, useContext } from 'react';
import { getAccounts } from '../api/client';
import { AuthContext } from '../AuthContext';

// Ordered list matching seed.py ACCOUNTS — IDs resolved at runtime from account_ids.json
export const SEEDED_NAMES = [
    'Arjun Sharma',
    'Priya Mehta',
    'Rohan Verma',
    'Sneha Iyer',
    'Karan Malhotra',
    'Ananya Bose',
    'Vikram Nair',
    'Deepika Rao',
    'Suspicious Actor',
    'Test Merchant',
];

const POLL_MS = 3000;

export function useAccounts(accountIds = [], activeAlerts = []) {
    const { token } = useContext(AuthContext);
    const [accounts, setAccounts] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    const fetchAccounts = useCallback(async () => {
        if (!token || accountIds.length === 0) return;
        try {
            const data = await getAccounts(token, accountIds);
            // Attach isHighRisk based on activeAlerts
            const alertAccountIds = new Set(activeAlerts.map((a) => a.account_id));
            const enriched = data.map((acc) => ({
                ...acc,
                isHighRisk: alertAccountIds.has(acc.id),
            }));
            setAccounts(enriched);
            setError(null);
        } catch (err) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    }, [token, accountIds, activeAlerts]);

    useEffect(() => {
        fetchAccounts();
        const id = setInterval(fetchAccounts, POLL_MS);
        return () => clearInterval(id);
    }, [fetchAccounts]);

    return { accounts, loading, error, refetch: fetchAccounts };
}
