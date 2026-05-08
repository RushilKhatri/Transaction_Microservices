/**
 * src/AuthContext.jsx
 * Provides the JWT token globally to all child components.
 */
import { createContext, useState, useEffect, useCallback } from 'react';
import { getToken } from './api/client';

export const AuthContext = createContext({ token: null, authError: null });

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

    return (
        <AuthContext.Provider value={{ token, authError, loading, retry: authenticate }}>
            {children}
        </AuthContext.Provider>
    );
}
