/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{vue,js}'],
  theme: {
    extend: {
      colors: {
        // Shared blue scale used by both the customer portal and admin sidebars.
        primary: {
          50: '#eff6ff',
          100: '#dbeafe',
          200: '#bfdbfe',
          300: '#93c5fd',
          400: '#60a5fa',
          500: '#3b82f6',
          600: '#2563eb',
          700: '#1d4ed8',
          800: '#1e40af',
          900: '#1e3a8a',
        },
        // Customer portal only.
        success: { 50: '#f0fdf4', 500: '#22c55e', 600: '#16a34a' },
        warning: { 500: '#f59e0b' },
        danger: { 500: '#ef4444' },
        // Admin only.
        purple: { 500: '#8b5cf6', 600: '#7c3aed' },
      },
    },
  },
  plugins: [],
};
