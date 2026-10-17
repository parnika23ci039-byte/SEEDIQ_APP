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
  ChevronUp,
  Shield,
  User as UserIcon,
  Clock,
} from "lucide-react";
import { SeedIQLogo } from "./logo";
import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useAuth, UserRole } from "@/lib/auth-context";

interface NavItem {
  title: string;
  url: string;
  icon: any;
  roles: UserRole[];
}

const ALL_NAV_ITEMS: NavItem[] = [
  { title: "Dashboard", url: "/dashboard", icon: LayoutDashboard, roles: ["Admin", "Researcher", "Farmer", "Guest"] },
  { title: "Crop AI", url: "/crop-ai", icon: Sprout, roles: ["Admin", "Researcher", "Farmer", "Guest"] },
  { title: "Yield AI", url: "/yield-ai", icon: TrendingUp, roles: ["Admin", "Researcher", "Farmer", "Guest"] },
  { title: "Seed AI", url: "/seed-ai", icon: TestTubes, roles: ["Admin", "Researcher", "Farmer", "Guest"] },
  { title: "Quantum Lab", url: "/quantum", icon: Atom, roles: ["Admin", "Researcher", "Guest"] },
  { title: "Storage AI", url: "/storage-ai", icon: Warehouse, roles: ["Admin", "Researcher", "Farmer", "Guest"] },
  { title: "Upload Data", url: "/upload", icon: Upload, roles: ["Admin", "Researcher"] },
  { title: "My Datasets", url: "/database", icon: Database, roles: ["Admin", "Researcher"] },
  { title: "Admin Console", url: "/admin", icon: ShieldCheck, roles: ["Admin"] },
];

export function AppSidebar() {
  const path = useRouterState({ select: (s) => s.location.pathname });
  const navigate = useNavigate();
  const { user, logout, guestTimeRemaining, formatGuestTime } = useAuth();
  const [showProfileMenu, setShowProfileMenu] = useState(false);

  const handleLogout = async () => {
    await logout();
  };

  const role: UserRole = user?.role || "Farmer";
  const displayName = user?.display_name || user?.name || user?.username || "Operator";
  const userInitial = displayName.charAt(0).toUpperCase();

  // Dynamic role-filtered navigation
  const visibleNav = ALL_NAV_ITEMS.filter((item) => item.roles.includes(role));

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

  return (
    <aside className="sticky top-0 hidden h-screen w-72 shrink-0 flex-col border-r border-white/5 bg-black/40 backdrop-blur-xl shadow-[4px_0_24px_-4px_rgba(0,0,0,0.4)] lg:flex relative">
      <div className="border-b border-white/5 p-6">
        <SeedIQLogo />
      </div>

      <nav className="flex-1 space-y-1 overflow-y-auto p-4">
        {visibleNav.map((item) => {
          const active = path === item.url;
          const Icon = item.icon;
          return (
            <Link
              key={item.url}
              to={item.url}
              className={[
                "group relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm transition-all",
                active
                  ? "text-emerald-400 border border-emerald-500/30 bg-emerald-500/10 shadow-[0_0_15px_-3px_hsl(150_70%_45%/0.2)]"
                  : "text-white/60 hover:bg-white/5 hover:text-white",
              ].join(" ")}
            >
              {active && (
                <span className="absolute inset-y-2 left-0 w-[3px] rounded-full bg-emerald-400 shadow-[0_0_12px_hsl(150_70%_45%)]" />
              )}
              <Icon
                className={`h-4 w-4 ${
                  active ? "text-emerald-400" : "text-white/40 group-hover:text-emerald-400"
                }`}
              />
              <span className="font-medium tracking-tight">{item.title}</span>
              {active && (
                <span className="ml-auto h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
              )}
            </Link>
          );
        })}
      </nav>

      <div className="border-t border-white/5 p-4 relative">
        {/* Guest 5-Minute Timeout Warning Banner */}
        {user?.isGuest && (
          <div className="mb-3 rounded-2xl border border-amber-500/30 bg-amber-950/30 p-3 text-xs shadow-[0_0_15px_rgba(245,158,11,0.15)]">
            <div className="flex items-center justify-between text-[10px] font-mono font-bold text-amber-400">
              <span className="flex items-center gap-1.5">
                <Clock className="h-3 w-3 animate-pulse" />
                GUEST PREVIEW
              </span>
              <span className="bg-amber-950 px-2 py-0.5 rounded-full border border-amber-500/40">
                {formatGuestTime(guestTimeRemaining)}
              </span>
            </div>
            <div className="mt-2 h-1.5 w-full rounded-full bg-black/50 overflow-hidden border border-amber-500/20">
              <div
                className="h-full bg-gradient-to-r from-amber-500 to-orange-400 transition-all duration-1000"
                style={{ width: `${Math.min(100, Math.max(0, ((guestTimeRemaining || 0) / 300) * 100))}%` }}
              />
            </div>
            <div className="mt-1.5 text-[9px] text-amber-200/70">
              Max 5 minutes preview. Sign in to save workspace models.
            </div>
          </div>
        )}

        {/* QPU status pill */}
        <div className="mb-3 rounded-xl border border-white/5 bg-black/40 p-3">
          <div className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-widest text-emerald-400">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
            QML Simulator
          </div>
          <div className="mt-2 flex items-baseline justify-between">
            <span className="font-display text-lg text-white">Local QPU</span>
            <span className="text-[10px] uppercase tracking-widest text-white/50">Running</span>
          </div>
        </div>

        {/* Account Profile Bar */}
        <div className="relative">
          <div
            onClick={() => setShowProfileMenu(!showProfileMenu)}
            className="flex items-center gap-3 rounded-xl border border-white/5 bg-black/40 p-3 transition hover:bg-white/5 cursor-pointer"
          >
            <div
              className={`grid h-9 w-9 shrink-0 place-items-center rounded-full bg-gradient-to-br ${getAvatarGradient(
                role
              )} font-display text-sm font-semibold text-white shadow-[0_0_15px_-3px_hsl(150_70%_45%/0.5)]`}
            >
              {userInitial}
            </div>
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-medium text-white">{displayName}</div>
              <div className="flex items-center gap-1.5 mt-0.5">
                <span
                  className={`rounded border px-1.5 py-0.2 text-[9px] font-bold uppercase tracking-wider ${getRoleBadgeStyle(
                    role
                  )}`}
                >
                  {role}
                </span>
                <span className="text-[10px] text-white/40 truncate">{user?.email || "seediq.local"}</span>
              </div>
            </div>
            <ChevronUp
              className={`h-4 w-4 text-white/40 transition-transform ${
                showProfileMenu ? "rotate-180" : ""
              }`}
            />
          </div>

          {/* Account Profile Popover */}
          <AnimatePresence>
            {showProfileMenu && (
              <motion.div
                initial={{ opacity: 0, y: 10, scale: 0.95 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, scale: 0.95 }}
                className="absolute bottom-full left-0 right-0 mb-2 rounded-2xl border border-white/10 bg-[#08100c] p-3 shadow-2xl backdrop-blur-2xl z-40"
              >
                <div className="mb-2.5 pb-2 border-b border-white/10">
                  <div className="text-xs font-semibold text-white">{displayName}</div>
                  <div className="text-[11px] text-white/50 truncate">{user?.email}</div>
                  <div className="mt-1 flex items-center gap-1.5">
                    <Shield className="h-3 w-3 text-emerald-400" />
                    <span className="text-[10px] font-bold text-emerald-300 uppercase">
                      {role} Access Tier
                    </span>
                  </div>
                </div>

                <button
                  onClick={handleLogout}
                  className="flex w-full items-center justify-center gap-2 rounded-xl border border-red-500/20 bg-red-500/10 py-2 text-xs font-semibold text-red-400 transition hover:bg-red-500/20 cursor-pointer"
                >
                  <LogOut className="h-3.5 w-3.5" />
                  <span>Log Out</span>
                </button>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </aside>
  );
}
