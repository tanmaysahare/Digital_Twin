import type { Config } from 'tailwindcss';

// Tailwind is mapped onto the design tokens rather than used with its default
// scale. A class that resolves to a colour outside tokens.css cannot exist,
// which is what keeps the greyscale rule enforceable in markup as well as CSS.
const config: Config = {
  content: ['./src/**/*.{ts,tsx}'],
  theme: {
    colors: {
      transparent: 'transparent',
      paper: 'var(--paper)',
      'paper-sunk': 'var(--paper-sunk)',
      'paper-raised': 'var(--paper-raised)',
      ink: 'var(--ink)',
      'ink-2': 'var(--ink-2)',
      'ink-3': 'var(--ink-3)',
      'ink-4': 'var(--ink-4)',
      rule: 'var(--rule)',
      'rule-strong': 'var(--rule-strong)',
      'state-drift': 'var(--state-drift)',
      'state-blocked': 'var(--state-blocked)',
      'state-starved': 'var(--state-starved)',
      'state-down': 'var(--state-down)',
      'state-forecast': 'var(--state-forecast)',
      'state-defect': 'var(--state-defect)',
      'state-dark': 'var(--state-dark)',
      accent: 'var(--accent)',
      'accent-quiet': 'var(--accent-quiet)',
      'series-1': 'var(--series-1)',
      'series-2': 'var(--series-2)',
      'series-3': 'var(--series-3)',
      band: 'var(--band)',
      baseline: 'var(--baseline)',
    },
    spacing: {
      0: '0',
      1: 'var(--space-1)',
      2: 'var(--space-2)',
      3: 'var(--space-3)',
      4: 'var(--space-4)',
      6: 'var(--space-6)',
      8: 'var(--space-8)',
      12: 'var(--space-12)',
    },
    borderRadius: {
      none: 'var(--radius-none)',
      DEFAULT: 'var(--radius)',
    },
    fontFamily: {
      sans: 'var(--font-sans)',
      mono: 'var(--font-mono)',
    },
    fontSize: {
      display: ['var(--text-display)', 'var(--text-display-line)'],
      title: ['var(--text-title)', 'var(--text-title-line)'],
      section: ['var(--text-section)', 'var(--text-section-line)'],
      body: ['var(--text-body)', 'var(--text-body-line)'],
      label: ['var(--text-label)', 'var(--text-label-line)'],
      small: ['var(--text-small)', 'var(--text-small-line)'],
      micro: ['var(--text-micro)', 'var(--text-micro-line)'],
    },
    boxShadow: {
      none: 'none',
      overlay: 'var(--elevation-overlay)',
    },
    extend: {
      borderColor: {
        DEFAULT: 'var(--rule)',
      },
    },
  },
  plugins: [],
};

export default config;
