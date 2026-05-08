/**
 * src/App.jsx
 * Root application component.
 * - Manages AuthContext
 * - Loads account IDs from the notification service or falls back to /data/account_ids.json
 * - Calls all hooks at the top level and passes data down as props
 */
import { useContext, useEffect, useState } from 'react';
import { AuthContext } from './AuthContext';
import { useAlerts } from './hooks/useAlerts';
import { useAccounts } from './hooks/useAccounts';
import { useTransactions } from './hooks/useTransactions';

import StatCards from './components/StatCards';
import TransactionForm from './components/TransactionForm';
import TransactionFeed from './components/TransactionFeed';
import AccountBalances from './components/AccountBalances';
import FraudAlertBanner from './components/FraudAlertBanner';
import ServiceStatus from './components/ServiceStatus';

import './App.css';

// ── Inner App (needs token from context) ─────────────────────────────────────

function Dashboard() {
    const { token, authError } = useContext(AuthContext);

    // Load account IDs from the JSON file seeded by seed.py
    const [accountIds, setAccountIds] = useState([]);
    const [idsError, setIdsError] = useState(null);

    useEffect(() => {
        fetch('/account_ids.json')
            .then((r) => {
                if (!r.ok) throw new Error(`Cannot load account_ids.json (HTTP ${r.status})`);
                return r.json();
            })
            .then((data) => {
                // data is { "Arjun Sharma": "<uuid>", ... } — extract values
                const ids = Object.values(data);
                setAccountIds(ids);
            })
            .catch((err) => {
                setIdsError(err.message);
            });
    }, []);

    // Hooks — all data fetching lives here
    const { alerts, activeAlerts, dismissAlert } = useAlerts();
    const { accounts, error: accError, refetch: refetchAccounts } = useAccounts(accountIds, activeAlerts);
    const { transactions, error: txError, refetch: refetchTransactions } = useTransactions(accountIds, accounts);

    const handleTransactionSuccess = () => {
        refetchAccounts();
        refetchTransactions();
    };

    if (authError) {
        return (
            <div className="auth-error-banner" role="alert">
                <span>🔴</span>
                <strong>Cannot reach transaction service</strong> — is it running?
                <br />
                <small>{authError}</small>
            </div>
        );
    }

    return (
        <>
            <FraudAlertBanner
                activeAlerts={activeAlerts}
                dismissAlert={dismissAlert}
                accounts={accounts}
            />

            <main className="main-content">
                {idsError && (
                    <div className="inline-error ids-error">
                        ⚠️ Could not load account_ids.json: {idsError}.{' '}
                        <em>Copy data/account_ids.json to frontend/public/ after running seed.py.</em>
                    </div>
                )}

                <StatCards transactions={transactions} activeAlerts={activeAlerts} />

                <div className="two-col-panel">
                    <TransactionForm
                        accounts={accounts}
                        onSuccess={handleTransactionSuccess}
                    />
                    <TransactionFeed transactions={transactions} error={txError} />
                </div>

                <AccountBalances accounts={accounts} error={accError} />
            </main>
        </>
    );
}

// ── Root component with AuthContext wrapper ───────────────────────────────────

import { AuthProvider } from './AuthContext';

export default function App() {
    return (
        <AuthProvider>
            <div className="app-shell">
                <header className="app-header">
                    <div className="header-left">
                        <span className="header-logo">🏦</span>
                        <h1 className="header-title">SecureBank — transaction monitor</h1>
                    </div>
                    <ServiceStatus />
                </header>
                <Dashboard />
            </div>
        </AuthProvider>
    );
}
