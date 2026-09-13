import { motion, useScroll, useTransform } from "framer-motion";
import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";

/* ── Particle canvas ─────────────────────────────────────────── */
function ParticleCanvas() {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d")!;
    let raf: number;

    const resize = () => {
      canvas.width = canvas.offsetWidth * window.devicePixelRatio;
      canvas.height = canvas.offsetHeight * window.devicePixelRatio;
      ctx.scale(window.devicePixelRatio, window.devicePixelRatio);
    };
    resize();
    window.addEventListener("resize", resize, { passive: true });

    const W = () => canvas.offsetWidth;
    const H = () => canvas.offsetHeight;

    const COLORS = ["0,149,255", "103,58,228", "0,215,223"];

    const particles = Array.from({ length: 90 }, () => ({
      x: Math.random() * W(),
      y: Math.random() * H(),
      vx: (Math.random() - 0.5) * 0.25,
      vy: (Math.random() - 0.5) * 0.25,
      r: Math.random() * 1.8 + 0.4,
      color: COLORS[Math.floor(Math.random() * COLORS.length)],
      opacity: Math.random() * 0.55 + 0.1,
    }));

    const draw = () => {
      ctx.clearRect(0, 0, W(), H());

      for (let i = 0; i < particles.length; i++) {
        const p = particles[i];
        // connections
        for (let j = i + 1; j < particles.length; j++) {
          const q = particles[j];
          const dx = p.x - q.x, dy = p.y - q.y;
          const dist = Math.sqrt(dx * dx + dy * dy);
          if (dist < 130) {
            ctx.beginPath();
            ctx.strokeStyle = `rgba(0,149,255,${0.08 * (1 - dist / 130)})`;
            ctx.lineWidth = 0.5;
            ctx.moveTo(p.x, p.y);
            ctx.lineTo(q.x, q.y);
            ctx.stroke();
          }
        }
        // dot
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(${p.color},${p.opacity})`;
        ctx.fill();

        p.x += p.vx;
        p.y += p.vy;
        if (p.x < 0 || p.x > W()) p.vx *= -1;
        if (p.y < 0 || p.y > H()) p.vy *= -1;
      }
      raf = requestAnimationFrame(draw);
    };
    draw();

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
    };
  }, []);

  return (
    <canvas
      ref={ref}
      className="absolute inset-0 w-full h-full pointer-events-none"
      style={{ opacity: 0.7 }}
    />
  );
}

/* ── Animated counter ────────────────────────────────────────── */
function Counter({ to, suffix = "" }: { to: number; suffix?: string }) {
  const ref = useRef<HTMLSpanElement>(null);
  const started = useRef(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const observer = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting && !started.current) {
        started.current = true;
        const duration = 1800;
        const start = performance.now();
        const step = (now: number) => {
          const t = Math.min((now - start) / duration, 1);
          const ease = 1 - Math.pow(1 - t, 3);
          el.textContent = Math.floor(ease * to).toLocaleString() + suffix;
          if (t < 1) requestAnimationFrame(step);
        };
        requestAnimationFrame(step);
      }
    }, { threshold: 0.5 });

    observer.observe(el);
    return () => observer.disconnect();
  }, [to, suffix]);

  return <span ref={ref}>0{suffix}</span>;
}

/* ── Hero ────────────────────────────────────────────────────── */
const METRICS = [
  { label: "Goals Completed",   value: 12400, suffix: "+" },
  { label: "Specialized Agents", value: 5,    suffix: "" },
  { label: "Tools Available",    value: 7,    suffix: "" },
  { label: "Tasks / Minute",     value: 240,  suffix: "+" },
];

export function HeroSection() {
  const nav = useNavigate();
  const { scrollY } = useScroll();
  const y = useTransform(scrollY, [0, 500], [0, 80]);
  const opacity = useTransform(scrollY, [0, 400], [1, 0]);

  return (
    <section className="relative min-h-screen flex flex-col items-center justify-center overflow-hidden pt-24">
      {/* Background glows */}
      <div className="absolute inset-0 bg-hero-glow pointer-events-none" />
      <div className="absolute inset-0 bg-hero-glow-purple pointer-events-none" />
      <div className="absolute top-1/4 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[700px] h-[700px] rounded-full bg-accent/8 blur-[180px] pointer-events-none animate-glow-pulse" />
      <div className="absolute top-1/3 left-1/3 w-[400px] h-[400px] rounded-full bg-purple/6 blur-[140px] pointer-events-none animate-glow-pulse" style={{ animationDelay: "1.5s" }} />

      {/* Particle canvas */}
      <ParticleCanvas />

      {/* Content */}
      <motion.div
        style={{ y, opacity }}
        className="relative z-10 flex flex-col items-center text-center px-6 max-w-6xl mx-auto"
      >
        {/* Badge */}
        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.2, duration: 0.5 }}
          className="inline-flex items-center gap-2 rounded-full px-4 py-1.5 mb-8 glass-card text-xs font-medium tracking-widest uppercase text-accent border-accent/20"
        >
          <span className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse-ring" />
          Now in Public Beta
        </motion.div>

        {/* Headline */}
        <motion.h1
          initial={{ opacity: 0, y: 32 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3, duration: 0.7, ease: [0.16, 1, 0.3, 1] }}
          className="font-display font-bold text-gradient leading-[1.04] tracking-tight mb-6"
          style={{ fontSize: "clamp(3rem, 8vw, 7rem)" }}
        >
          The Multi-Agent Platform<br />
          <span className="text-gradient-blue">for Autonomous AI</span>
        </motion.h1>

        {/* Sub */}
        <motion.p
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.45, duration: 0.6 }}
          className="max-w-2xl text-text-dim text-lg leading-relaxed mb-10"
        >
          Delegate any goal. omniBox decomposes it into a precise task graph, spins up
          specialized agents, invokes real tools, and delivers results—end to end.
          No workflows to configure. Just delegate.
        </motion.p>

        {/* CTAs */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.6, duration: 0.5 }}
          className="flex flex-wrap items-center justify-center gap-4"
        >
          <button
            onClick={() => nav("/app")}
            className="btn-neon text-white font-semibold px-8 py-3.5 rounded-full text-base tracking-wide"
          >
            Start Delegating →
          </button>
          <a
            href="#features"
            className="btn-glass text-white font-medium px-8 py-3.5 rounded-full text-base"
          >
            See How It Works
          </a>
        </motion.div>

        {/* Floating orb visual */}
        <motion.div
          initial={{ opacity: 0, scale: 0.8 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.8, duration: 1, ease: "easeOut" }}
          className="relative mt-20 w-64 h-64"
        >
          <div className="absolute inset-0 rounded-full bg-gradient-radial from-accent/20 via-purple/10 to-transparent blur-xl animate-float" />
          <div className="absolute inset-8 rounded-full bg-gradient-radial from-accent/30 via-purple/15 to-transparent blur-lg animate-float" style={{ animationDelay: "0.5s" }} />
          <div className="absolute inset-16 rounded-full bg-gradient-radial from-accent/50 to-purple/30 blur-md" />
          <svg className="absolute inset-0 w-full h-full opacity-20" viewBox="0 0 200 200">
            <circle cx="100" cy="100" r="90" stroke="rgba(0,149,255,0.4)" strokeWidth="0.5" fill="none" />
            <circle cx="100" cy="100" r="70" stroke="rgba(103,58,228,0.4)" strokeWidth="0.5" fill="none" />
            <circle cx="100" cy="100" r="50" stroke="rgba(0,215,223,0.4)" strokeWidth="0.5" fill="none" />
          </svg>
        </motion.div>
      </motion.div>

      {/* Metrics ribbon */}
      <div className="relative z-10 w-full max-w-6xl mx-auto px-6 mt-16 mb-0">
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 1.0, duration: 0.6 }}
          className="glass-card rounded-2xl grid grid-cols-2 md:grid-cols-4 divide-x divide-y md:divide-y-0"
          style={{ borderColor: "rgba(255,255,255,0.07)" }}
        >
          {METRICS.map((m) => (
            <div key={m.label} className="flex flex-col items-center justify-center py-6 px-4 gap-1">
              <span className="font-display font-bold text-3xl text-white">
                <Counter to={m.value} suffix={m.suffix} />
              </span>
              <span className="text-xs text-text-muted tracking-wide uppercase">{m.label}</span>
            </div>
          ))}
        </motion.div>
      </div>

      {/* Bottom fade */}
      <div className="absolute bottom-0 inset-x-0 h-40 bg-gradient-to-t from-black to-transparent pointer-events-none" />
    </section>
  );
}
