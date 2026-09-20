/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Civic navy. Municipal, calm, not a startup gradient.
        ink: {
          50: '#F5F7FA', 100: '#E8EDF3', 200: '#CFD9E5', 300: '#A7B8CD',
          400: '#7590B0', 500: '#4F6E93', 600: '#385475', 700: '#1B4571',
          800: '#123252', 900: '#0B2239', 950: '#06182A',
        },
        brand: {
          50: '#EEF5FC', 100: '#D8E8F7', 200: '#B0D0EE', 300: '#7FB2E1',
          400: '#4F90D0', 500: '#2F72B8', 600: '#215A98', 700: '#1B4779',
          800: '#173A61', 900: '#143051',
        },
        // Saffron accent, used sparingly for calls to action.
        accent: {
          50: '#FEF5EC', 100: '#FCE7D0', 200: '#F8CA9E', 300: '#F2A868',
          400: '#EC8B3C', 500: '#DD7120', 600: '#BC5817', 700: '#964217',
          800: '#7A3619', 900: '#652E18',
        },
        success: { 50: '#ECFAF3', 100: '#D1F3E3', 500: '#1E9E6A', 600: '#168055', 700: '#136045' },
        warn: { 50: '#FEF8EC', 100: '#FBEECF', 500: '#D99A1F', 600: '#B37B15' },
        danger: { 50: '#FDF0F0', 100: '#FADCDC', 500: '#D14343', 600: '#B23333', 700: '#8F2A2A' },
        // Priority bands - the single most repeated visual signal in the app.
        p1: '#D14343',
        p2: '#E07B39',
        p3: '#D9A520',
        p4: '#4F90D0',
      },
      fontFamily: {
        sans: ['Inter', 'Noto Sans Devanagari', 'Nirmala UI', 'system-ui', 'sans-serif'],
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
      fontSize: {
        '2xs': ['0.6875rem', { lineHeight: '1rem' }],
      },
      boxShadow: {
        card: '0 1px 2px rgba(11,34,57,0.05), 0 1px 3px rgba(11,34,57,0.06)',
        lift: '0 4px 12px rgba(11,34,57,0.09), 0 2px 4px rgba(11,34,57,0.05)',
        pop: '0 12px 32px rgba(11,34,57,0.16)',
      },
      borderRadius: { xl: '0.75rem', '2xl': '1rem' },
      keyframes: {
        'fade-in': { from: { opacity: '0', transform: 'translateY(4px)' }, to: { opacity: '1', transform: 'none' } },
        'slide-up': { from: { opacity: '0', transform: 'translateY(12px)' }, to: { opacity: '1', transform: 'none' } },
        shimmer: { '100%': { transform: 'translateX(100%)' } },
      },
      animation: {
        'fade-in': 'fade-in 180ms ease-out',
        'slide-up': 'slide-up 240ms cubic-bezier(0.22,1,0.36,1)',
      },
    },
  },
  plugins: [],
}
