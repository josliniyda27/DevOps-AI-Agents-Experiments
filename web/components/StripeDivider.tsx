/** The M tricolor stripe: a 4px brand-identity divider. Never a button or a fill. */
export function StripeDivider({ animate = true }: { animate?: boolean }) {
  return (
    <div
      aria-hidden
      className={`h-1 w-full origin-left bg-[linear-gradient(90deg,var(--color-m-blue-light)_0_33.34%,var(--color-m-blue-dark)_33.34%_66.67%,var(--color-m-red)_66.67%_100%)] ${
        animate ? "motion-safe:animate-stripe-in" : ""
      }`}
    />
  );
}
