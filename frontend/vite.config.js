import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
    plugins: [react()],
    server: {
        port: 3000,
        open: true,
        proxy: {
            '/api/transaction': 'http://localhost:5001',
            '/api/fraud': 'http://localhost:5002',
            '/api/notification': 'http://localhost:5003',
        },
    },
});
