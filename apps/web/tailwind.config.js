/** @type {import('tailwindcss').Config} */
const token = (name) => `rgb(var(--${name}) / <alpha-value>)`;

export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        surface: token("surface"),
        raised: token("raised"),
        sunken: token("sunken"),
        ink: token("ink"),
        muted: token("muted"),
        line: token("line"),
        field: token("field"),
        brand: { DEFAULT: token("brand"), ink: token("brand-ink") },
        pos: token("pos"),
        neg: token("neg"),
        warn: token("warn"),
      },
      fontFamily: {
        sans: ['"IBM Plex Sans"', "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
      },
      // One shape scale: controls lg (8px), cards xl (12px), sheets/dialogs 2xl (16px), chips full.
      borderRadius: { lg: "0.5rem", xl: "0.75rem", "2xl": "1rem" },
      boxShadow: {
        card: "0 1px 2px rgb(var(--shadow) / 0.04), 0 1px 1px rgb(var(--shadow) / 0.03)",
        pop: "0 12px 32px -8px rgb(var(--shadow) / 0.18), 0 2px 6px rgb(var(--shadow) / 0.08)",
      },
      keyframes: {
        fadeUp: {
          from: { opacity: "0", transform: "translateY(4px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        shimmer: { "100%": { transform: "translateX(100%)" } },
        blink: { "50%": { opacity: "0" } },
      },
      animation: {
        fadeUp: "fadeUp .2s cubic-bezier(0.16, 1, 0.3, 1) both",
        shimmer: "shimmer 1.4s infinite",
        caret: "blink 1s steps(1) infinite",
      },
    },
  },
  plugins: [],
};
