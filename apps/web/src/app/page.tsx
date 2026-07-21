import { AppHeader } from "@/components/layout/app-header";
import { BottomNavigation } from "@/components/layout/bottom-navigation";
import { CreatorExplorer } from "@/components/creators/creator-explorer";

export default function HomePage() {
  return (
    <main className="min-h-screen bg-[var(--surface)] pb-24 text-[var(--surface-foreground)]">
      <AppHeader />
      <CreatorExplorer />
      <BottomNavigation />
    </main>
  );
}
