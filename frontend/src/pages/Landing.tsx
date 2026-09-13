import { Navbar } from "../components/landing/Navbar";
import { HeroSection } from "../components/landing/HeroSection";
import { FeaturesSection } from "../components/landing/FeaturesSection";
import { HowItWorks } from "../components/landing/HowItWorks";
import { BlogReel } from "../components/landing/BlogReel";
import { PartnersMarquee } from "../components/landing/PartnersMarquee";
import { LandingFooter } from "../components/landing/LandingFooter";

export function Landing() {
  return (
    <div className="bg-black min-h-screen">
      <Navbar />
      <HeroSection />
      <FeaturesSection />
      <HowItWorks />
      <BlogReel />
      <PartnersMarquee />
      <LandingFooter />
    </div>
  );
}
