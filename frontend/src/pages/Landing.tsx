import { Navbar } from "../components/landing/Navbar";
import { HeroSection } from "../components/landing/HeroSection";
import { HowItWorks } from "../components/landing/HowItWorks";
import { FeaturesSection } from "../components/landing/FeaturesSection";
import { ProofSection } from "../components/landing/ProofSection";
import { StackSection } from "../components/landing/StackSection";
import { LandingFooter } from "../components/landing/LandingFooter";

export function Landing() {
  return (
    <div className="min-h-screen">
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
