import { LandingNav } from "../components/landing/LandingNav";
import { Hero } from "../components/landing/Hero";
import { HowItRuns } from "../components/landing/HowItRuns";
import { Agents } from "../components/landing/Agents";
import { Toolbox } from "../components/landing/Toolbox";
import { ProofEconomy } from "../components/landing/ProofEconomy";
import { Reliability } from "../components/landing/Reliability";
import { ClosingCta } from "../components/landing/ClosingCta";
import { SiteFooter } from "../components/landing/SiteFooter";

export function Landing() {
  return (
    <div className="min-h-screen bg-paper font-manrope text-ink antialiased">
      <LandingNav />
      <main>
        <Hero />
        <HowItRuns />
        <Agents />
        <Toolbox />
        <ProofEconomy />
        <Reliability />
        <ClosingCta />
      </main>
      <SiteFooter />
    </div>
  );
}
