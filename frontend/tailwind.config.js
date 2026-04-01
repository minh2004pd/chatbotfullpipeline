/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Dark theme palette
        bg: {
          primary: '#0f0f0f',
          secondary: '#1a1a1a',
          tertiary: '#242424',
          hover: '#2a2a2a',
          border: '#2e2e2e',
        },
        accent: {
          DEFAULT: '#7c3aed',
          hover: '#6d28d9',
          light: '#8b5cf6',
          subtle: '#1e1035',
        },
        text: {
          primary: '#f1f1f1',
          secondary: '#a0a0a0',
          muted: '#666666',
        },
        user: {
          bg: '#1e1035',
          border: '#4c1d95',
        },
        assistant: {
          bg: '#1a1a1a',
          border: '#2e2e2e',
        },
        success: '#10b981',
        warning: '#f59e0b',
        error: '#ef4444',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
      animation: {
        'cursor-blink': 'blink 1s step-end infinite',
        'fade-in': 'fadeIn 0.2s ease-in-out',
        'slide-up': 'slideUp 0.2s ease-out',
        'spin-slow': 'spin 2s linear infinite',
      },
      keyframes: {
        blink: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0' },
        },
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { transform: 'translateY(8px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
      },
      typography: {
        DEFAULT: {
          css: {
            color: '#f1f1f1',
            a: { color: '#8b5cf6' },
            strong: { color: '#f1f1f1' },
            code: { color: '#e2e8f0' },
            h1: { color: '#f1f1f1' },
            h2: { color: '#f1f1f1' },
            h3: { color: '#f1f1f1' },
            h4: { color: '#f1f1f1' },
            blockquote: { color: '#a0a0a0', borderLeftColor: '#4c1d95' },
            'ul > li::marker': { color: '#7c3aed' },
            'ol > li::marker': { color: '#7c3aed' },
            hr: { borderColor: '#2e2e2e' },
            pre: { backgroundColor: '#0f0f0f' },
          },
        },
      },
    },
  },
  plugins: [
    // prose plugin inline styles via custom typography config above
  ],
}
