// The six icons. DESIGN_SYSTEM.md Section 8.
//
// There is no icon library installed and there will not be one, because
// installing one guarantees more icons appear. Each of these earns its place by
// repeating often enough that the shape becomes the label. Everything else in
// this product is a word.
//
// 16px, 1.5px stroke, --ink-2, and none of them is decorative.

interface IconProps {
  className?: string;
}

const BASE = 'inline-block align-[-2px] text-ink-2';

export function Chevron({ className = '' }: IconProps) {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      aria-hidden="true"
      className={`${BASE} ${className}`}
    >
      <path d="M6 4l4 4-4 4" />
    </svg>
  );
}

export function ArrowUp({ className = '' }: IconProps) {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      aria-hidden="true"
      className={`${BASE} ${className}`}
    >
      <path d="M8 12V4M4.5 7.5L8 4l3.5 3.5" />
    </svg>
  );
}

export function ArrowDown({ className = '' }: IconProps) {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      aria-hidden="true"
      className={`${BASE} ${className}`}
    >
      <path d="M8 4v8M4.5 8.5L8 12l3.5-3.5" />
    </svg>
  );
}

// The interval rule, endpoints marked. It appears beside any interval-valued
// number, which on this line is every dark station on every screen.
export function IntervalRule({ className = '' }: IconProps) {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      aria-hidden="true"
      className={`${BASE} ${className}`}
    >
      <path d="M3 8h10M3 5.5v5M13 5.5v5" />
    </svg>
  );
}

// The hatch swatch. A dark station is not an alarm, it is a fact, so it gets a
// pattern rather than a colour.
export function HatchSwatch({ className = '' }: IconProps) {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 16 16"
      aria-hidden="true"
      className={`${BASE} ${className}`}
    >
      <defs>
        <pattern
          id="hatch-swatch"
          width="4"
          height="4"
          patternTransform="rotate(45)"
          patternUnits="userSpaceOnUse"
        >
          <line
            x1="0"
            y1="0"
            x2="0"
            y2="4"
            stroke="currentColor"
            strokeWidth="1.5"
          />
        </pattern>
      </defs>
      <rect
        x="2.5"
        y="2.5"
        width="11"
        height="11"
        fill="url(#hatch-swatch)"
        stroke="currentColor"
        strokeWidth="1"
      />
    </svg>
  );
}

export function Cross({ className = '' }: IconProps) {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      aria-hidden="true"
      className={`${BASE} ${className}`}
    >
      <path d="M4 4l8 8M12 4l-8 8" />
    </svg>
  );
}
