/**
 * src/components/TransactionForm.jsx
 * Left panel card: send a transaction between two accounts.
 */
import { useState, useContext } from 'react';
import { postTransaction } from '../api/client';
import { AuthContext } from '../AuthContext';

const INR = (v) => v.toLocaleString('en-IN', { style: 'currency', currency: 'INR' });

export default function TransactionForm({ accounts, onSuccess }) {
    const { token } = useContext(AuthContext);
    const [fromId, setFromId] = useState('');
    const [toId, setToId] = useState('');
    const [amount, setAmount] = useState('');
    const [result, setResult] = useState(null); // { type: 'success'|'fraud'|'rejected'|'error', msg, data }
    const [submitting, setSubmitting] = useState(false);

    const clearResult = () => {
        setTimeout(() => setResult(null), 5000);
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        if (!fromId || !toId || !amount) return;
        if (fromId === toId) {
            setResult({ type: 'error', msg: 'From and To accounts must be different.' });
            clearResult();
            return;
        }
        setSubmitting(true);
        setResult(null);
        try {
            const data = await postTransaction(token, {
                fromAccountId: fromId,
                toAccountId: toId,
                amount: parseFloat(amount),
            });

            if (data.fraud_flagged) {
                setResult({
                    type: 'fraud',
                    msg: `Transaction completed but FRAUD FLAGGED — Score: ${(
                        data.fraud_score * 100
                    ).toFixed(0)}% — Rules triggered: ${data.rules_triggered || 'N/A'}`,
                    data,
                });
            } else {
                setResult({
                    type: 'success',
                    msg: `Transaction successful — ID: ${data.id?.slice(0, 8)}…`,
                    data,
                });
            }
            // Trigger immediate re-fetch without waiting for polling
            if (onSuccess) onSuccess();
        } catch (err) {
            if (err.message.includes('Insufficient') || err.message.includes('422')) {
                setResult({ type: 'rejected', msg: 'Rejected — insufficient balance' });
            } else {
                setResult({ type: 'error', msg: err.message });
            }
        } finally {
            setSubmitting(false);
            clearResult();
        }
    };

    const toOptions = accounts.filter((a) => a.id !== fromId);

    return (
        <div className="card form-card">
            <h2 className="card-title">Send Transaction</h2>
            <form onSubmit={handleSubmit} className="tx-form">
                <label className="form-label">
                    From Account
                    <select
                        className="form-select"
                        value={fromId}
                        onChange={(e) => {
                            setFromId(e.target.value);
                            if (toId === e.target.value) setToId('');
                        }}
                        required
                    >
                        <option value="">— select sender —</option>
                        {accounts.map((acc) => (
                            <option key={acc.id} value={acc.id}>
                                {acc.isHighRisk ? '🔴 ' : ''}{acc.owner_name} — {INR(acc.balance)}
                            </option>
                        ))}
                    </select>
                </label>

                <label className="form-label">
                    To Account
                    <select
                        className="form-select"
                        value={toId}
                        onChange={(e) => setToId(e.target.value)}
                        required
                    >
                        <option value="">— select receiver —</option>
                        {toOptions.map((acc) => (
                            <option key={acc.id} value={acc.id}>
                                {acc.isHighRisk ? '🔴 ' : ''}{acc.owner_name} — {INR(acc.balance)}
                            </option>
                        ))}
                    </select>
                </label>

                <label className="form-label">
                    Amount (₹)
                    <input
                        className="form-input"
                        type="number"
                        min="1"
                        step="0.01"
                        placeholder="e.g. 55,000"
                        value={amount}
                        onChange={(e) => setAmount(e.target.value)}
                        required
                    />
                </label>

                <button className="btn-primary" type="submit" disabled={submitting}>
                    {submitting ? 'Processing…' : 'Send Transaction'}
                </button>
            </form>

            {result && (
                <div className={`tx-result tx-result--${result.type}`} role="status">
                    {result.type === 'success' && '✅ '}
                    {result.type === 'fraud' && '🚨 '}
                    {result.type === 'rejected' && '⚠️ '}
                    {result.type === 'error' && '❌ '}
                    {result.msg}
                </div>
            )}
        </div>
    );
}
