import { Navbar } from "../components/landing/Navbar";
import { HeroSection } from "../components/landing/HeroSection";
import { FeaturesSection } from "../components/landing/FeaturesSection";
import { HowItWorks } from "../components/landing/HowItWorks";
import { BlogReel } from "../components/landing/BlogReel";
import { PartnersMarquee } from "../components/landing/PartnersMarquee";
import { LandingFooter } from "../components/landing/LandingFooter";

/* Persistent full-page background that sits behind every section */
function PageBackground() {
  return (
    <div className="fixed inset-0 pointer-events-none z-0" aria-hidden>
      {/* Base: pure black */}
      <div className="absolute inset-0 bg-black" />

      {/* Subtle dot grid */}
      <div
        className="absolute inset-0 opacity-[0.18]"
        style={{
          backgroundImage:
            "radial-gradient(circle, rgba(255,255,255,0.55) 1px, transparent 1px)",
          backgroundSize: "32px 32px",
        }}
      />

      {/* Top-centre hero glow — fades as user scrolls but grid remains */}
      <div
        className="absolute -top-40 left-1/2 -translate-x-1/2 w-[900px] h-[600px] rounded-full opacity-30 animate-glow-pulse"
        style={{
          background:
            "radial-gradient(ellipse at center, rgba(0,149,255,0.35) 0%, rgba(103,58,228,0.15) 45%, transparent 70%)",
          filter: "blur(80px)",
        }}
      />

      {/* Mid-page accent — creates ambient light as you scroll */}
      <div
        className="absolute top-[120vh] left-[15%] w-[600px] h-[500px] rounded-full opacity-20 animate-glow-pulse"
        style={{
          background:
            "radial-gradient(ellipse at center, rgba(103,58,228,0.4) 0%, transparent 65%)",
          filter: "blur(100px)",
          animationDelay: "1.2s",
        }}
      />
      <div
        className="absolute top-[120vh] right-[10%] w-[500px] h-[500px] rounded-full opacity-15 animate-glow-pulse"
        style={{
          background:
            "radial-gradient(ellipse at center, rgba(0,149,255,0.35) 0%, transparent 65%)",
          filter: "blur(120px)",
          animationDelay: "2.4s",
        }}
      />

      {/* Lower-page glow */}
      <div
        className="absolute top-[240vh] left-1/2 -translate-x-1/2 w-[700px] h-[500px] rounded-full opacity-20 animate-glow-pulse"
        style={{
          background:
            "radial-gradient(ellipse at center, rgba(0,149,255,0.28) 0%, rgba(103,58,228,0.18) 50%, transparent 70%)",
          filter: "blur(100px)",
          animationDelay: "0.8s",
        }}
      />

      {/* Bottom CTA glow */}
      <div
        className="absolute top-[360vh] left-1/2 -translate-x-1/2 w-[800px] h-[600px] rounded-full opacity-25 animate-glow-pulse"
        style={{
          background:
            "radial-gradient(ellipse at center, rgba(0,149,255,0.3) 0%, rgba(103,58,228,0.2) 45%, transparent 68%)",
          filter: "blur(90px)",
          animationDelay: "1.8s",
        }}
      />
    </div>
  );
}

export function Landing() {
  return (
    <div className="relative min-h-screen" style={{ background: "#000" }}>
      <PageBackground />

      {/* All content layers above the fixed background */}
      <div className="relative z-10">
        <Navbar />
        <HeroSection />
        <FeaturesSection />
        <HowItWorks />
        <BlogReel />
        <PartnersMarquee />
        <LandingFooter />
      </div>
    </div>
  );
}
