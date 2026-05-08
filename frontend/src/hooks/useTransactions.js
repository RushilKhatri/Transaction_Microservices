/**
 * src/hooks/useTransactions.js
 * Polls transaction history for all accounts every 3 seconds.
 * Resolves account names from the accounts list.
 */
import { useState, useEffect, useCallback, useContext } from 'react';
import { getAllTransactionHistory } from '../api/client';
import { AuthContext } from '../AuthContext';

const POLL_MS = 3000;

export function useTransactions(accountIds = [], accounts = []) {
    const { token } = useContext(AuthContext);
    const [transactions, setTransactions] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    // Build a lookup map from account ID → owner_name
    const nameMap = accounts.reduce((m, a) => {
        m[a.id] = a.owner_name;
        return m;
    }, {});

    const fetchTransactions = useCallback(async () => {
        if (!token || accountIds.length === 0) return;
        try {
            const txs = await getAllTransactionHistory(token, accountIds);
            // Attach resolved names
            const enriched = txs.map((tx) => ({
                ...tx,
                from_name: nameMap[tx.from_account_id] || tx.from_account_id.slice(0, 8),
                to_name: nameMap[tx.to_account_id] || tx.to_account_id.slice(0, 8),
            }));
            setTransactions(enriched);
            setError(null);
        } catch (err) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    }, [token, accountIds, JSON.stringify(nameMap)]);

    useEffect(() => {
        fetchTransactions();
        const id = setInterval(fetchTransactions, POLL_MS);
        return () => clearInterval(id);
    }, [fetchTransactions]);

    return { transactions, loading, error, refetch: fetchTransactions };
}
