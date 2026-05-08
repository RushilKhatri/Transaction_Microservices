/**
 * src/hooks/useAlerts.js
 * Polls GET /alerts every 3 seconds.
 * Provides dismissAlert() function with optimistic update + re-fetch.
 */
import { useState, useEffect, useCallback, useContext } from 'react';
import { getAlerts, dismissAlert as apiDismissAlert } from '../api/client';
import { AuthContext } from '../AuthContext';

const POLL_MS = 3000;

export function useAlerts() {
    const { token } = useContext(AuthContext);
    const [alerts, setAlerts] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    const fetchAlerts = useCallback(async () => {
        if (!token) return;
        try {
            const data = await getAlerts(token);
            setAlerts(Array.isArray(data) ? data : []);
            setError(null);
        } catch (err) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    }, [token]);

    useEffect(() => {
        fetchAlerts();
        const id = setInterval(fetchAlerts, POLL_MS);
        return () => clearInterval(id);
    }, [fetchAlerts]);

    const dismissAlert = useCallback(
        async (alertId) => {
            // Optimistic update
            setAlerts((prev) =>
                prev.map((a) => (a.id === alertId ? { ...a, dismissed: true } : a))
            );
            try {
                await apiDismissAlert(token, alertId);
                await fetchAlerts(); // re-fetch to sync with server
            } catch (err) {
                // Revert optimistic update on failure
                setAlerts((prev) =>
                    prev.map((a) => (a.id === alertId ? { ...a, dismissed: false } : a))
                );
                setError(err.message);
            }
        },
        [token, fetchAlerts]
    );

    const activeAlerts = alerts.filter((a) => !a.dismissed);

    return { alerts, activeAlerts, dismissAlert, loading, error, refetch: fetchAlerts };
}
