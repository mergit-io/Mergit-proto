/** Shared fixed background for every /app page — the light Aurora wash. */
export function AppBackground() {
  return (
    <div className="fixed inset-0 -z-10 pointer-events-none" aria-hidden>
      <div className="absolute inset-0 bg-paper" />
      <div className="absolute -left-40 -top-52 h-[620px] w-[680px] rounded-full bg-[radial-gradient(circle_at_40%_40%,rgba(228,214,255,0.55),rgba(228,214,255,0)_68%)] blur-2xl" />
      <div className="absolute -right-40 -top-40 h-[600px] w-[660px] rounded-full bg-[radial-gradient(circle_at_60%_40%,rgba(255,220,198,0.45),rgba(255,220,198,0)_66%)] blur-2xl" />
      <div className="absolute -bottom-56 left-1/3 h-[560px] w-[720px] rounded-full bg-[radial-gradient(circle_at_50%_50%,rgba(201,243,226,0.4),rgba(201,243,226,0)_66%)] blur-3xl" />
    </div>
  );
}
