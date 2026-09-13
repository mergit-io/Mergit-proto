import { motion } from "framer-motion";
import { ArrowRight } from "lucide-react";

const POSTS = [
  {
    tag: "Launch",
    title: "Introducing omniBox: Autonomous Multi-Agent AI",
    desc: "We built an open-ended goal delegation system from the ground up. Here's the architecture behind the orchestrator, agent runner, and tool layer.",
    date: "May 2026",
    gradient: "from-accent/20 via-purple/10 to-transparent",
  },
  {
    tag: "Engineering",
    title: "Building Restart-Resumable Agent Workflows",
    desc: "How we made long-running multi-agent workflows survive crashes, restarts, and network drops using SQLite WAL and idempotent tool execution.",
    date: "May 2026",
    gradient: "from-purple/20 via-cyan/10 to-transparent",
  },
  {
    tag: "Deep Dive",
    title: "Tool Use at Scale: From Web Search to GitHub PRs",
    desc: "An inside look at the tool registry, idempotency keys, and how we prevent duplicate side-effects when agents retry failed tasks.",
    date: "May 2026",
    gradient: "from-cyan/20 via-accent/10 to-transparent",
  },
];

export function BlogReel() {
  return (
    <section className="relative py-32 px-6 overflow-hidden">
      <div className="absolute top-0 inset-x-0 h-px bg-gradient-to-r from-transparent via-white/6 to-transparent" />

      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="flex items-end justify-between mb-12"
        >
          <div>
            <p className="text-accent text-sm font-semibold uppercase tracking-widest mb-3">What's New</p>
            <h2 className="font-display font-bold text-gradient" style={{ fontSize: "clamp(2rem, 4vw, 3rem)" }}>
              From the Team
            </h2>
          </div>
          <a href="#" className="hidden sm:flex items-center gap-2 text-sm text-text-dim hover:text-white transition-colors group">
            View all
            <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
          </a>
        </motion.div>

        {/* Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          {POSTS.map((post, i) => (
            <motion.a
              key={post.title}
              href="#"
              initial={{ opacity: 0, y: 28 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.1, duration: 0.55 }}
              className="group glass-card rounded-3xl overflow-hidden flex flex-col hover:border-white/14 transition-all duration-300"
              style={{ textDecoration: "none" }}
            >
              {/* Image area */}
              <div
                className={`h-48 bg-gradient-to-br ${post.gradient} relative overflow-hidden`}
                style={{ background: undefined }}
              >
                <div className={`absolute inset-0 bg-gradient-to-br ${post.gradient}`} />
                <div className="absolute inset-0 bg-black/20" />
                {/* Abstract decorative circles */}
                <div className="absolute -top-8 -right-8 w-32 h-32 rounded-full border border-white/5" />
                <div className="absolute -bottom-4 -left-4 w-24 h-24 rounded-full border border-white/5" />
                <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-16 h-16 rounded-full bg-white/4 blur-xl" />
                {/* Tag */}
                <span className="absolute top-4 left-4 text-xs font-semibold px-3 py-1 rounded-full bg-black/40 border border-white/10 text-white backdrop-blur-sm">
                  {post.tag}
                </span>
              </div>

              {/* Content */}
              <div className="flex flex-col flex-1 p-6 gap-3">
                <h3 className="font-display font-semibold text-white text-base leading-snug group-hover:text-accent-2 transition-colors duration-200">
                  {post.title}
                </h3>
                <p className="text-text-muted text-sm leading-relaxed line-clamp-2 flex-1">
                  {post.desc}
                </p>
                <div className="flex items-center justify-between mt-2">
                  <span className="text-xs text-text-muted">{post.date}</span>
                  <span className="flex items-center gap-1.5 text-xs text-accent font-medium group-hover:gap-2.5 transition-all duration-200">
                    Read more
                    <ArrowRight className="w-3.5 h-3.5" />
                  </span>
                </div>
              </div>
            </motion.a>
          ))}
        </div>
      </div>
    </section>
  );
}
