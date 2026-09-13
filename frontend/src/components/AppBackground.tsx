/** Shared fixed background for all /app pages — same dot grid + ambient orbs as Landing. */
export function AppBackground() {
  return (
    <div className="fixed inset-0 pointer-events-none z-0" aria-hidden>
      {/* Base */}
      <div className="absolute inset-0 bg-black" />

      {/* Dot grid */}
      <div
        className="absolute inset-0 opacity-[0.14]"
        style={{
          backgroundImage: "radial-gradient(circle, rgba(255,255,255,0.55) 1px, transparent 1px)",
          backgroundSize: "32px 32px",
        }}
      />

      {/* Top-right accent orb */}
      <div
        className="absolute -top-32 -right-32 w-[640px] h-[640px] rounded-full opacity-20 animate-glow-pulse"
        style={{
          background: "radial-gradient(ellipse at center, rgba(0,149,255,0.4) 0%, rgba(103,58,228,0.18) 45%, transparent 70%)",
          filter: "blur(90px)",
        }}
      />

      {/* Bottom-left purple orb */}
      <div
        className="absolute -bottom-40 -left-20 w-[500px] h-[500px] rounded-full opacity-15 animate-glow-pulse"
        style={{
          background: "radial-gradient(ellipse at center, rgba(103,58,228,0.45) 0%, transparent 65%)",
          filter: "blur(100px)",
          animationDelay: "1.8s",
        }}
      />

      {/* Subtle centre wash */}
      <div
        className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[700px] h-[400px] rounded-full opacity-[0.06] animate-glow-pulse"
        style={{
          background: "radial-gradient(ellipse at center, rgba(0,149,255,0.6) 0%, transparent 70%)",
          filter: "blur(120px)",
          animationDelay: "0.9s",
        }}
      />
    </div>
  );
}
