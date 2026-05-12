/**
 * src/AuthContext.jsx
 * Provides the JWT token globally to all child components.
 */
import { createContext, useState, useEffect, useCallback } from 'react';
import { getToken } from './api/client';

export const AuthContext = createContext({ token: null, authError: null });

const AUTH_RETRY_MS = 10000;

export function AuthProvider({ children }) {
    const [token, setToken] = useState(null);
    const [authError, setAuthError] = useState(null);
    const [loading, setLoading] = useState(true);

    const authenticate = useCallback(async () => {
        try {
            const t = await getToken();
            setToken(t);
            setAuthError(null);
        } catch (err) {
            setAuthError(err.message);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        authenticate();
    }, [authenticate]);

    useEffect(() => {
        if (token || !authError || loading) return undefined;

        const timer = setTimeout(() => {
            authenticate();
        }, AUTH_RETRY_MS);

        return () => clearTimeout(timer);
    }, [token, authError, loading, authenticate]);

    return (
        <AuthContext.Provider value={{ token, authError, loading, retry: authenticate }}>
            {children}
        </AuthContext.Provider>
    );
}
