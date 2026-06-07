/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      // Design token palette — dark-first premium dashboard aesthetic
      colors: {
        // Surface layers (darkest → lightest)
        surface: {
          0: '#0a0c10',   // page background
          1: '#111318',   // base card background
          2: '#181c24',   // elevated card / sidebar
          3: '#1f2430',   // input fields, hover states
          4: '#262d3d',   // borders, dividers (subtle)
          5: '#2e3750',   // borders (stronger), selection bg
        },
        // Accent — electric blue-violet (primary interactive)
        accent: {
          50: '#eef2ff',
          100: '#e0e7ff',
          200: '#c7d2fe',
          300: '#a5b4fc',
          400: '#818cf8',
          500: '#6366f1',  // primary
          600: '#4f46e5',
          700: '#4338ca',
          800: '#3730a3',
          900: '#312e81',
        },
        // Semantic status
        ok:     { DEFAULT: '#22c55e', muted: '#16a34a20' },
        warn:   { DEFAULT: '#f59e0b', muted: '#d9770620' },
        error:  { DEFAULT: '#ef4444', muted: '#dc262620' },
        info:   { DEFAULT: '#38bdf8', muted: '#0ea5e920' },
        // Text hierarchy
        text: {
          primary:   '#f0f4ff',
          secondary: '#8b9cbf',
          muted:     '#4a5568',
          inverse:   '#0a0c10',
        },
      },

      // Large, dashboard-appropriate typography scale
      fontSize: {
        'display': ['4.5rem',  { lineHeight: '1.05', letterSpacing: '-0.03em', fontWeight: '700' }],
        'title-xl': ['2.5rem', { lineHeight: '1.1',  letterSpacing: '-0.02em', fontWeight: '700' }],
        'title-lg': ['1.875rem',{ lineHeight: '1.2',  letterSpacing: '-0.015em', fontWeight: '600' }],
        'title':    ['1.5rem', { lineHeight: '1.3',  letterSpacing: '-0.01em', fontWeight: '600' }],
        'body-lg':  ['1.125rem',{ lineHeight: '1.6' }],
        'body':     ['1rem',   { lineHeight: '1.6' }],
        'body-sm':  ['0.875rem',{ lineHeight: '1.5' }],
        'caption':  ['0.75rem',{ lineHeight: '1.4', letterSpacing: '0.02em' }],
        'label':    ['0.6875rem',{ lineHeight: '1', letterSpacing: '0.08em', fontWeight: '600', textTransform: 'uppercase' }],
      },

      fontFamily: {
        sans: [
          'Inter',
          'system-ui',
          '-apple-system',
          'BlinkMacSystemFont',
          'Segoe UI',
          'sans-serif',
        ],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },

      // Smooth, purposeful animations
      transitionDuration: {
        fast: '120ms',
        base: '200ms',
        slow: '350ms',
        xslow: '600ms',
      },
      transitionTimingFunction: {
        spring: 'cubic-bezier(0.34, 1.56, 0.64, 1)',
        ease:   'cubic-bezier(0.4, 0, 0.2, 1)',
        out:    'cubic-bezier(0, 0, 0.2, 1)',
        in:     'cubic-bezier(0.4, 0, 1, 1)',
      },

      keyframes: {
        'fade-in': {
          '0%':   { opacity: '0', transform: 'translateY(6px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'fade-out': {
          '0%':   { opacity: '1', transform: 'translateY(0)' },
          '100%': { opacity: '0', transform: 'translateY(6px)' },
        },
        'scale-in': {
          '0%':   { opacity: '0', transform: 'scale(0.96)' },
          '100%': { opacity: '1', transform: 'scale(1)' },
        },
        'slide-up': {
          '0%':   { transform: 'translateY(100%)' },
          '100%': { transform: 'translateY(0)' },
        },
        'pulse-ring': {
          '0%, 100%': { boxShadow: '0 0 0 0 rgba(99,102,241,0.4)' },
          '50%':       { boxShadow: '0 0 0 8px rgba(99,102,241,0)' },
        },
        'spin': {
          '100%': { transform: 'rotate(360deg)' },
        },
        'shimmer': {
          '0%':   { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
      },

      animation: {
        'fade-in':    'fade-in 200ms cubic-bezier(0,0,0.2,1) both',
        'fade-out':   'fade-out 150ms cubic-bezier(0.4,0,1,1) both',
        'scale-in':   'scale-in 200ms cubic-bezier(0.34,1.56,0.64,1) both',
        'slide-up':   'slide-up 300ms cubic-bezier(0,0,0.2,1) both',
        'pulse-ring': 'pulse-ring 2s ease infinite',
        'spin':       'spin 800ms linear infinite',
        'shimmer':    'shimmer 1.5s linear infinite',
      },

      borderRadius: {
        'card': '1rem',
        'pill': '9999px',
      },

      boxShadow: {
        'card':    '0 1px 3px rgba(0,0,0,0.5), 0 4px 16px rgba(0,0,0,0.3)',
        'card-lg': '0 4px 24px rgba(0,0,0,0.5), 0 16px 48px rgba(0,0,0,0.3)',
        'glow':    '0 0 24px rgba(99,102,241,0.35)',
        'glow-sm': '0 0 12px rgba(99,102,241,0.25)',
        'inner':   'inset 0 1px 0 rgba(255,255,255,0.05)',
        'none':    'none',
      },

      backdropBlur: {
        'xs':  '2px',
        'card': '12px',
      },

      spacing: {
        'touch': '44px',  // minimum touch target per HIG
      },
    },
  },
  plugins: [],
};
