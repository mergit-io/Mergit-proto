import { useEffect } from "react";
import { Navbar } from "../components/landing/Navbar";
import { HeroSection } from "../components/landing/HeroSection";
import { HowItWorks } from "../components/landing/HowItWorks";
import { FeaturesSection } from "../components/landing/FeaturesSection";
import { ProofSection } from "../components/landing/ProofSection";
import { StackSection } from "../components/landing/StackSection";
import { LandingFooter } from "../components/landing/LandingFooter";
import { useReveal } from "../hooks/useReveal";

export function Landing() {
  useReveal();

  /* `.landing-moss` below re-points the design tokens for this subtree, but the
     document's own background belongs to <html> and would still show through an
     overscroll bounce as the console's near-black. This hands the page's ground
     to the scene for as long as the landing is mounted, and gives it back on the
     way to /app. */
  useEffect(() => {
    document.documentElement.dataset.landing = "moss";
    return () => {
      delete document.documentElement.dataset.landing;
    };
  }, []);

  return (
    <div className="landing-moss min-h-screen">
      <Navbar />
      <HeroSection />
      <HowItWorks />
      <FeaturesSection />
      <ProofSection />
      <StackSection />
      <LandingFooter />
    </div>
  );
}
