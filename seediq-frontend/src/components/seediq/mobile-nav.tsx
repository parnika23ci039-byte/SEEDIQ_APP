import { Link, useRouterState, useNavigate } from "@tanstack/react-router";
import {
  LayoutDashboard,
  Sprout,
  TrendingUp,
  TestTubes,
  Atom,
  Warehouse,
  Upload,
  Database,
  ShieldCheck,
  LogOut,
  X,
  Menu,
  MoreHorizontal,
  Clock,
  Shield,
  Layers,
} from "lucide-react";
import { SeedIQLogo } from "./logo";
import { motion, AnimatePresence } from "framer-motion";
import { useAuth, UserRole } from "@/lib/auth-context";

interface NavItem {
  title: string;
  shortTitle: string;
  url: string;
  icon: any;
  roles: UserRole[];
}

export const ALL_MOBILE_NAV_ITEMS: NavItem[] = [
  { title: "Dashboard", shortTitle: "Dashboard", url: "/dashboard", icon: LayoutDashboard, roles: ["Admin", "Researcher", "Farmer", "Guest"] },
  { title: "Crop AI", shortTitle: "Crop AI", url: "/crop-ai", icon: Sprout, roles: ["Admin", "Researcher", "Farmer", "Guest"] },
  { title: "Yield AI", shortTitle: "Yield AI", url: "/yield-ai", icon: TrendingUp, roles: ["Admin", "Researcher", "Farmer", "Guest"] },
  { title: "Seed AI", shortTitle: "Seed AI", url: "/seed-ai", icon: TestTubes, roles: ["Admin", "Researcher", "Farmer", "Guest"] },
  { title: "Storage AI", shortTitle: "Storage AI", url: "/storage-ai", icon: Warehouse, roles: ["Admin", "Researcher", "Farmer", "Guest"] },
  { title: "Quantum Lab", shortTitle: "Quantum", url: "/quantum", icon: Atom, roles: ["Admin", "Researcher", "Guest"] },
  { title: "Upload Data", shortTitle: "Upload", url: "/upload", icon: Upload, roles: ["Admin", "Researcher"] },
  { title: "My Datasets", shortTitle: "Datasets", url: "/database", icon: Database, roles: ["Admin", "Researcher"] },
  { title: "Admin Console", shortTitle: "Admin", url: "/admin", icon: ShieldCheck, roles: ["Admin"] },
];

// 4 primary quick-tabs for bottom taskbar
const PRIMARY_BOTTOM_BAR_TABS = [
  { title: "Dashboard", url: "/dashboard", icon: LayoutDashboard },
  { title: "Crop AI", url: "/crop-ai", icon: Sprout },
  { title: "Yield AI", url: "/yield-ai", icon: TrendingUp },
  { title: "Storage AI", url: "/storage-ai", icon: Warehouse },
];

interface MobileNavigationProps {
  isOpen: boolean;
  onClose: () => void;
  onToggle: () => void;
}

export function MobileNavigation({ isOpen, onClose, onToggle }: MobileNavigationProps) {
  const path = useRouterState({ select: (s) => s.location.pathname });
  const navigate = useNavigate();
  const { user, logout, guestTimeRemaining, formatGuestTime } = useAuth();

  const role: UserRole = user?.role || "Farmer";
  const displayName = user?.display_name || user?.name || user?.username || "Operator";
  const userInitial = displayName.charAt(0).toUpperCase();

  const visibleNav = ALL_MOBILE_NAV_ITEMS.filter((item) => item.roles.includes(role));

  const handleLogout = async () => {
    onClose();
    await logout();
  };

  const getRoleBadgeStyle = (r: UserRole) => {
    switch (r) {
      case "Admin":
        return "bg-amber-500/20 text-amber-300 border-amber-500/40";
      case "Researcher":
        return "bg-sky-500/20 text-sky-300 border-sky-500/40";
      case "Farmer":
        return "bg-emerald-500/20 text-emerald-300 border-emerald-500/40";
      case "Guest":
        return "bg-purple-500/20 text-purple-300 border-purple-500/40";
      default:
        return "bg-white/10 text-white/70 border-white/10";
    }
  };

  const getAvatarGradient = (r: UserRole) => {
    switch (r) {
      case "Admin":
        return "from-amber-500 to-emerald-600";
      case "Researcher":
        return "from-sky-500 to-indigo-600";
      case "Farmer":
        return "from-emerald-500 to-teal-600";
      case "Guest":
        return "from-purple-500 to-slate-700";
      default:
        return "from-emerald-500 to-teal-600";
    }
  };

  // Check if current route is one of the 4 primary tabs
  const isPrimaryTabActive = PRIMARY_BOTTOM_BAR_TABS.some((tab) => tab.url === path);
  const isMoreActive = !isPrimaryTabActive;

  return (
    <>
      {/* ========================================================================= */}
      {/* 1. FIXED MOBILE BOTTOM TASKBAR (Visible on screens < lg)                   */}
      {/* ========================================================================= */}
      <nav
        aria-label="Mobile Bottom Taskbar"
        className="fixed bottom-0 left-0 right-0 z-40 block lg:hidden border-t border-white/10 bg-[#020b06]/95 backdrop-blur-2xl shadow-[0_-8px_30px_rgba(0,0,0,0.85)] pb-[max(env(safe-area-inset-bottom),0.5rem)] pt-1.5"
      >
        <div className="grid grid-cols-5 items-center px-1">
          {PRIMARY_BOTTOM_BAR_TABS.map((tab) => {
            const active = path === tab.url;
            const Icon = tab.icon;
            return (
              <Link
                key={tab.url}
                to={tab.url}
                onClick={onClose}
                className={[
                  "relative flex flex-col items-center justify-center py-1 px-1 rounded-xl transition-all duration-200",
                  active
                    ? "text-emerald-400 font-semibold"
                    : "text-white/60 hover:text-white active:scale-95",
                ].join(" ")}
              >
                {active && (
                  <motion.span
                    layoutId="mobile-taskbar-active"
                    className="absolute -top-1.5 h-1 w-8 rounded-full bg-emerald-400 shadow-[0_0_12px_hsl(150_70%_45%)]"
                    transition={{ type: "spring", stiffness: 400, damping: 30 }}
                  />
                )}
                <div
                  className={`flex h-8 w-8 items-center justify-center rounded-xl transition-colors ${
                    active ? "bg-emerald-500/15 text-emerald-400" : "text-white/50"
                  }`}
                >
                  <Icon className="h-4 w-4" />
                </div>
                <span className="text-[10px] tracking-tight truncate max-w-[62px]">
                  {tab.title}
                </span>
              </Link>
            );
          })}

          {/* More / All Pages Toggle */}
          <button
            type="button"
            onClick={onToggle}
            className={[
              "relative flex flex-col items-center justify-center py-1 px-1 rounded-xl transition-all duration-200 active:scale-95",
              isOpen || isMoreActive
                ? "text-emerald-400 font-semibold"
                : "text-white/60 hover:text-white",
            ].join(" ")}
            aria-label="Toggle All Pages Menu"
          >
            {(isOpen || isMoreActive) && (
              <motion.span
                layoutId="mobile-taskbar-more-active"
                className="absolute -top-1.5 h-1 w-8 rounded-full bg-emerald-400 shadow-[0_0_12px_hsl(150_70%_45%)]"
                transition={{ type: "spring", stiffness: 400, damping: 30 }}
              />
            )}
            <div
              className={`flex h-8 w-8 items-center justify-center rounded-xl transition-colors ${
                isOpen || isMoreActive
                  ? "bg-emerald-500/15 text-emerald-400"
                  : "text-white/50"
              }`}
            >
              {isOpen ? <X className="h-4 w-4" /> : <Layers className="h-4 w-4" />}
            </div>
            <span className="text-[10px] tracking-tight">
              {isOpen ? "Close" : "All AI"}
            </span>
          </button>
        </div>
      </nav>

      {/* ========================================================================= */}
      {/* 2. FULL MOBILE SLIDE-OVER DRAWER (All Pages & Features for Phones)         */}
      {/* ========================================================================= */}
      <AnimatePresence>
        {isOpen && (
          <div className="fixed inset-0 z-50 lg:hidden flex">
            {/* Backdrop */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              onClick={onClose}
              className="fixed inset-0 bg-black/80 backdrop-blur-md"
            />

            {/* Slide-over Content */}
            <motion.div
              initial={{ x: "-100%" }}
              animate={{ x: 0 }}
              exit={{ x: "-100%" }}
              transition={{ type: "spring", damping: 28, stiffness: 300 }}
              className="relative z-10 flex h-full w-[85%] max-w-xs flex-col border-r border-white/10 bg-[#030d07] shadow-2xl pb-6"
            >
              {/* Header */}
              <div className="flex items-center justify-between border-b border-white/10 px-5 py-4">
                <SeedIQLogo size={36} />
                <button
                  type="button"
                  onClick={onClose}
                  className="flex h-8 w-8 items-center justify-center rounded-lg border border-white/10 bg-white/5 text-white/70 hover:bg-white/10 hover:text-white transition active:scale-95"
                  aria-label="Close menu"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>

              {/* User Card */}
              <div className="border-b border-white/10 p-4 bg-black/30">
                <div className="flex items-center gap-3">
                  <div
                    className={`grid h-10 w-10 shrink-0 place-items-center rounded-full bg-gradient-to-br ${getAvatarGradient(
                      role
                    )} font-display text-sm font-semibold text-white shadow-[0_0_15px_-3px_hsl(150_70%_45%/0.5)]`}
                  >
                    {userInitial}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm font-semibold text-white">
                      {displayName}
                    </div>
                    <div className="flex items-center gap-2 mt-0.5">
                      <span
                        className={`rounded border px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider ${getRoleBadgeStyle(
                          role
                        )}`}
                      >
                        {role}
                      </span>
                      <span className="text-[10px] text-white/40 truncate">
                        {user?.email || "seediq.local"}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Guest Timer countdown if guest */}
                {user?.isGuest && (
                  <div className="mt-3 rounded-xl border border-amber-500/30 bg-amber-950/40 p-2.5 text-xs">
                    <div className="flex items-center justify-between text-[10px] font-mono font-bold text-amber-300">
                      <span className="flex items-center gap-1.5">
                        <Clock className="h-3 w-3 animate-pulse" />
                        GUEST PREVIEW
                      </span>
                      <span className="bg-amber-950 px-2 py-0.5 rounded border border-amber-500/40">
                        {formatGuestTime(guestTimeRemaining)}
                      </span>
                    </div>
                  </div>
                )}
              </div>

              {/* Navigation Links (Scrollable) */}
              <nav className="flex-1 space-y-1 overflow-y-auto p-3">
                <div className="px-2 py-1 text-[10px] font-semibold uppercase tracking-widest text-emerald-400/80">
                  Navigation & Tools
                </div>
                {visibleNav.map((item) => {
                  const active = path === item.url;
                  const Icon = item.icon;
                  return (
                    <Link
                      key={item.url}
                      to={item.url}
                      onClick={onClose}
                      className={[
                        "group relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm transition-all",
                        active
                          ? "text-emerald-400 border border-emerald-500/30 bg-emerald-500/10 font-medium shadow-[0_0_15px_-3px_hsl(150_70%_45%/0.2)]"
                          : "text-white/70 hover:bg-white/5 hover:text-white",
                      ].join(" ")}
                    >
                      {active && (
                        <span className="absolute inset-y-2 left-0 w-[3px] rounded-full bg-emerald-400 shadow-[0_0_12px_hsl(150_70%_45%)]" />
                      )}
                      <Icon
                        className={`h-4 w-4 shrink-0 ${
                          active ? "text-emerald-400" : "text-white/40 group-hover:text-emerald-400"
                        }`}
                      />
                      <span className="truncate">{item.title}</span>
                      {active && (
                        <span className="ml-auto h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
                      )}
                    </Link>
                  );
                })}
              </nav>

              {/* Bottom Footer Actions */}
              <div className="border-t border-white/10 p-4 space-y-3 bg-black/40">
                <div className="flex items-center justify-between rounded-xl border border-white/5 bg-black/50 p-2.5">
                  <div className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-widest text-emerald-400">
                    <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
                    QML Engine
                  </div>
                  <span className="text-[10px] uppercase font-mono tracking-wider text-emerald-300">
                    Online
                  </span>
                </div>

                <button
                  type="button"
                  onClick={handleLogout}
                  className="flex w-full items-center justify-center gap-2 rounded-xl border border-red-500/30 bg-red-500/15 py-2.5 text-xs font-semibold text-red-400 transition hover:bg-red-500/25 active:scale-98"
                >
                  <LogOut className="h-3.5 w-3.5" />
                  <span>Log Out of SeedIQ</span>
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </>
  );
}
