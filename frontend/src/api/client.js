/**
 * src/api/client.js
 * Centralised API client. All functions return parsed JSON or throw a descriptive Error.
 * Each function that requires auth accepts the JWT token as its first argument.
 */

const TRANSACTION_URL =
    import.meta.env.VITE_TRANSACTION_URL || 'http://localhost:5001';
const FRAUD_URL =
    import.meta.env.VITE_FRAUD_URL || 'http://localhost:5002';
const NOTIFICATION_URL =
    import.meta.env.VITE_NOTIFICATION_URL || 'http://localhost:5003';

// ── Helpers ──────────────────────────────────────────────────────────────────

function authHeaders(token) {
    return {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
    };
}

async function handleResponse(res, label) {
    if (!res.ok) {
        let msg = `${label}: HTTP ${res.status}`;
        try {
            const body = await res.json();
            if (body.error) msg = `${label}: ${body.error}`;
        } catch (_) { /* ignore parse errors */ }
        throw new Error(msg);
    }
    return res.json();
}

// ── Auth ─────────────────────────────────────────────────────────────────────

/**
 * Obtain JWT token. No auth header needed.
 * @returns {Promise<string>} access_token
 */
export async function getToken() {
    const res = await fetch(`${TRANSACTION_URL}/auth/token`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: 'admin', password: 'admin123' }),
    });
    const data = await handleResponse(res, 'getToken');
    return data.access_token;
}

// ── Accounts ─────────────────────────────────────────────────────────────────

/**
 * Fetch a single account by ID.
 */
export async function getAccountBalance(token, accountId) {
    const res = await fetch(`${TRANSACTION_URL}/account/${accountId}`, {
        headers: authHeaders(token),
    });
    return handleResponse(res, `getAccountBalance(${accountId})`);
}

/**
 * Fetch all accounts given an array of account IDs.
 * Returns array of account objects; silently skips failed lookups.
 */
export async function getAccounts(token, accountIds) {
    const results = await Promise.allSettled(
        accountIds.map((id) => getAccountBalance(token, id))
    );
    return results
        .filter((r) => r.status === 'fulfilled')
        .map((r) => r.value);
}

// ── Transactions ─────────────────────────────────────────────────────────────

/**
 * POST a new transaction.
 */
export async function postTransaction(token, { fromAccountId, toAccountId, amount }) {
    const res = await fetch(`${TRANSACTION_URL}/transaction`, {
        method: 'POST',
        headers: authHeaders(token),
        body: JSON.stringify({
            from_account_id: fromAccountId,
            to_account_id: toAccountId,
            amount: Number(amount),
            transaction_type: 'debit',
        }),
    });
    return handleResponse(res, 'postTransaction');
}

/**
 * GET transaction history for one account.
 */
export async function getTransactionHistory(token, accountId) {
    const res = await fetch(`${TRANSACTION_URL}/history/${accountId}`, {
        headers: authHeaders(token),
    });
    return handleResponse(res, `getTransactionHistory(${accountId})`);
}

/**
 * GET merged transaction history across all given account IDs.
 * Deduplicates by transaction ID, sorts newest-first, returns top 20.
 */
export async function getAllTransactionHistory(token, accountIds) {
    const results = await Promise.allSettled(
        accountIds.map((id) => getTransactionHistory(token, id))
    );
    const merged = new Map();
    for (const r of results) {
        if (r.status === 'fulfilled' && Array.isArray(r.value)) {
            for (const tx of r.value) {
                merged.set(tx.id, tx);
            }
        }
    }
    return Array.from(merged.values())
        .sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
        .slice(0, 20);
}

// ── Alerts ───────────────────────────────────────────────────────────────────

/**
 * GET all alerts from the notification service.
 */
export async function getAlerts(token) {
    const res = await fetch(`${NOTIFICATION_URL}/alerts`, {
        headers: authHeaders(token),
    });
    return handleResponse(res, 'getAlerts');
}

/**
 * PATCH to dismiss a specific alert.
 */
export async function dismissAlert(token, alertId) {
    const res = await fetch(`${NOTIFICATION_URL}/alerts/${alertId}/dismiss`, {
        method: 'PATCH',
        headers: authHeaders(token),
    });
    return handleResponse(res, `dismissAlert(${alertId})`);
}

// ── Health ───────────────────────────────────────────────────────────────────

/**
 * Check health of a service. Returns true if healthy, false otherwise.
 */
export async function checkHealth(serviceUrl) {
    try {
        const res = await fetch(`${serviceUrl}/health`, { signal: AbortSignal.timeout(4000) });
        return res.ok;
    } catch (_) {
        return false;
    }
}

export { TRANSACTION_URL, FRAUD_URL, NOTIFICATION_URL };
