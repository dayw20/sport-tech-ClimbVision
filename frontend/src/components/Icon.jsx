// Tiny geometric SVG icons — no emoji anywhere in the app.
export const Icon = {
  Upload: (p) => (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" {...p}>
      <path d="M8 11V3M8 3L4.5 6.5M8 3L11.5 6.5M2.5 12.5V13A.5.5 0 003 13.5h10a.5.5 0 00.5-.5v-.5"
        stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  ),
  Grid: (p) => (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" {...p}>
      <rect x="2.5" y="2.5" width="11" height="11" rx="1" stroke="currentColor" strokeWidth="1.3"/>
      <path d="M2.5 8h11M8 2.5v11" stroke="currentColor" strokeWidth="1.3"/>
    </svg>
  ),
  Target: (p) => (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" {...p}>
      <circle cx="8" cy="8" r="5.5" stroke="currentColor" strokeWidth="1.3"/>
      <circle cx="8" cy="8" r="2" stroke="currentColor" strokeWidth="1.3"/>
      <path d="M8 1v2M8 13v2M1 8h2M13 8h2" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
    </svg>
  ),
  Figure: (p) => (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" {...p}>
      <circle cx="8" cy="3" r="1.5" stroke="currentColor" strokeWidth="1.3"/>
      <path d="M8 5v4M8 9l-2.5 4M8 9l2.5 4M5 7l3-1 3 1"
        stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  ),
  // Funnel / streams-converging "combine" icon
  Merge: (p) => (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" {...p}>
      <path d="M3 2v3c0 1.5 1 2.5 2.5 3L8 9l2.5-1c1.5-.5 2.5-1.5 2.5-3V2M8 9v5"
        stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  ),
  Check: (p) => (
    <svg width="12" height="12" viewBox="0 0 16 16" fill="none" {...p}>
      <path d="M3 8.5l3 3 7-7" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  ),
  X: (p) => (
    <svg width="12" height="12" viewBox="0 0 16 16" fill="none" {...p}>
      <path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
    </svg>
  ),
  Arrow: (p) => (
    <svg width="12" height="12" viewBox="0 0 16 16" fill="none" {...p}>
      <path d="M3 8h10M9 4l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  ),
  Reset: (p) => (
    <svg width="12" height="12" viewBox="0 0 16 16" fill="none" {...p}>
      <path d="M3 8a5 5 0 105-5M3 3v3h3"
        stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  ),
  External: (p) => (
    <svg width="10" height="10" viewBox="0 0 16 16" fill="none" {...p}>
      <path d="M9 3h4v4M13 3l-6 6M11 9v3H4V5h3"
        stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  ),
  Play: (p) => (
    <svg width="12" height="12" viewBox="0 0 16 16" fill="none" {...p}>
      <path d="M4 3l9 5-9 5V3z" fill="currentColor"/>
    </svg>
  ),
  Dot: (p) => (
    <svg width="6" height="6" viewBox="0 0 6 6" {...p}>
      <circle cx="3" cy="3" r="3" fill="currentColor"/>
    </svg>
  ),
};
