import { createFileRoute, Outlet, useNavigate } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { AppSidebar } from "@/components/seediq/app-sidebar";
import { Topbar } from "@/components/seediq/topbar";
import { MobileNavigation } from "@/components/seediq/mobile-nav";
import { InteractiveBackground } from "@/components/seediq/interactive-background";
import { Atom, ShieldAlert } from "lucide-react";

export const Route = createFileRoute("/_app")({
  component: AppLayout,
});

function AppLayout() {
  const { user, isLoading } = useAuth();
  const navigate = useNavigate();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [isMounted, setIsMounted] = useState(false);

  useEffect(() => {
    setIsMounted(true);
  }, []);

  // Synchronously resolve authenticated user from memory or localStorage for 0ms page transitions
  const activeUser = user || (typeof window !== "undefined" ? (() => {
    try {
      const saved = localStorage.getItem("seediq_auth_user");
      return saved ? JSON.parse(saved) : null;
    } catch {
      return null;
    }
  })() : null);

  useEffect(() => {
    // Only redirect if client is fully mounted and truly has no session in memory or storage
    if (isMounted && !activeUser && !isLoading) {
      navigate({ to: "/login" });
    }
  }, [isMounted, activeUser, isLoading, navigate]);

  // If client is mounted and has no active session, render clean redirect screen without artificial stall
  if (isMounted && !activeUser) {
    return (
      <div className="min-h-screen w-full flex flex-col items-center justify-center bg-[#020B06] text-white p-6">
        <div className="flex flex-col items-center gap-3 text-center">
          <div className="h-12 w-12 rounded-2xl bg-amber-500/10 border border-amber-500/30 grid place-items-center text-amber-400">
            <ShieldAlert className="h-6 w-6" />
          </div>
          <p className="text-xs font-mono text-muted-foreground">Authentication required. Redirecting to login...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="relative flex min-h-screen w-full bg-[#020B06] text-foreground font-sans">
      <InteractiveBackground />

      {/* Desktop Sidebar (visible on lg screens) */}
      <AppSidebar />

      <div className="relative z-10 flex min-w-0 flex-1 flex-col">
        {/* Topbar with mobile hamburger toggle */}
        <Topbar onOpenMobileMenu={() => setMobileMenuOpen(true)} />
        
        {/* Main Content with bottom padding on mobile to clear bottom taskbar */}
        <main className="flex-1 p-4 sm:p-6 md:p-10 pb-24 lg:pb-10">
          <Outlet />
        </main>
      </div>

      {/* Mobile Fixed Bottom Taskbar & Slide-over Drawer for phones (< lg) */}
      <MobileNavigation
        isOpen={mobileMenuOpen}
        onClose={() => setMobileMenuOpen(false)}
        onToggle={() => setMobileMenuOpen((prev) => !prev)}
      />
    </div>
  );
}
