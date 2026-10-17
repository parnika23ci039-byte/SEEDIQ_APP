import { CloudSun, Bell, Info, ShieldAlert, Cpu, AlertTriangle, ArrowRight, ShieldCheck, Truck, RefreshCw, Clock, Database, Warehouse, CheckCircle2, CheckCheck, X, Menu } from "lucide-react";
import { useState, useEffect, useCallback, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useAuth } from "@/lib/auth-context";
import { toast } from "sonner";
import {
  getActiveSeedAlerts,
  getActiveAlertsCount,
  getRiskColorTheme,
  DistrictSeedIntelligence,
  DISTRICT_SEED_INTELLIGENCE
} from "@/lib/seed-intelligence";

const CHECKED_SYNC_KEY = "seediq_last_checked_notification_sync";

interface TopbarProps {
  onOpenMobileMenu?: () => void;
}

interface DistrictNotificationItem {
  id: string;
  district_id: string;
  district_name: string;
  kannada_name: string;
  region?: string;
  crop: string;
  risk_level: "CRITICAL" | "WARNING" | "MONITOR" | "STABLE";
  current_viability: number;
  predicted_viability: number;
  stock_tons: number;
  capacity_tons: number;
  occupancy_pct?: number;
  moisture_risk: string;
  facility: string;
  safe_duration?: string;
  title?: string;
  message?: string;
  recommended_action?: string;
  timestamp?: string;
  time_ago?: string;
  redistribution_eligible?: boolean;
}

interface StorageNotificationResponse {
  status: string;
  last_synced: string;
  next_sync_in_seconds: number;
  sync_frequency_minutes: number;
  max_limit?: number;
  total_districts?: number;
  notifications_count?: number;
  active_alerts_count: number;
  critical_count: number;
  warning_count: number;
  monitor_count?: number;
  stable_count?: number;
  notifications?: DistrictNotificationItem[];
  alerts?: DistrictNotificationItem[];
}

export function Topbar({ onOpenMobileMenu }: TopbarProps = {}) {
  const { user, guestTimeRemaining, formatGuestTime } = useAuth();
  const [showNotifications, setShowNotifications] = useState(false);
  const [isSyncing, setIsSyncing] = useState(false);
  const [countdown, setCountdown] = useState(300);
  const [lastSyncFormatted, setLastSyncFormatted] = useState<string>("");
  const [currentSyncBatchTime, setCurrentSyncBatchTime] = useState<string>("");
  const [hasUnread, setHasUnread] = useState(false);
  const [notifications, setNotifications] = useState<DistrictNotificationItem[]>([]);
  const [alertCounts, setAlertCounts] = useState({ critical: 0, warning: 0, total: 0 });

  const panelRef = useRef<HTMLDivElement>(null);
  const bellButtonRef = useRef<HTMLButtonElement>(null);

  const fallbackSeedAlerts = getActiveSeedAlerts();

  // Fetch real-time 5-minute district storage notifications (up to 21 items)
  const fetchLiveNotifications = useCallback(async (isManual = false) => {
    setIsSyncing(true);
    try {
      const res = await fetch("/api/notifications/district-storage?limit=21");
      if (res.ok) {
        const data: StorageNotificationResponse = await res.json();
        const rawList = data.notifications || data.alerts || [];
        // Max 21 real-time notifications
        const list21 = rawList.slice(0, 21);
        setNotifications(list21);
        setAlertCounts({
          critical: data.critical_count || list21.filter(n => n.risk_level === "CRITICAL").length,
          warning: data.warning_count || list21.filter(n => n.risk_level === "WARNING").length,
          total: list21.length
        });
        setCountdown(data.next_sync_in_seconds || 300);

        const syncTime = data.last_synced || new Date().toISOString();
        setCurrentSyncBatchTime(syncTime);

        // Check if this sync batch has already been checked by the user
        const lastChecked = typeof window !== "undefined" ? localStorage.getItem(CHECKED_SYNC_KEY) : null;
        if (lastChecked && lastChecked === syncTime) {
          setHasUnread(false);
        } else {
          setHasUnread(true);
          if (!isManual && lastChecked) {
            toast.info("New 5-Minute District Telemetry Synced", {
              description: `${list21.length} real-time Karnataka storage alerts updated.`
            });
          }
        }

        const now = new Date();
        const timeStr = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        setLastSyncFormatted(timeStr);

        if (isManual) {
          toast.success(`Karnataka Live Alerts Synced (${list21.length} notifications)`, {
            description: `Refreshed at ${timeStr}. Auto-syncs every 5 minutes.`
          });
        }
        return;
      }
    } catch {
      // Fallback: build 21 prioritized Karnataka alerts from local intelligence
    }

    // Fallback: build up to 21 prioritized Karnataka district intelligence alerts
    const allDistricts = Object.values(DISTRICT_SEED_INTELLIGENCE);
    const riskPriority: Record<string, number> = { CRITICAL: 0, WARNING: 1, MONITOR: 2, STABLE: 3 };
    allDistricts.sort((a, b) => (riskPriority[a.riskLevel] ?? 4) - (riskPriority[b.riskLevel] ?? 4));

    const fallbackList: DistrictNotificationItem[] = allDistricts.slice(0, 21).map((d) => {
      const occupancy = d.riskLevel === "CRITICAL" ? 42 : d.riskLevel === "WARNING" ? 65 : 82;
      const capacity = 6000;
      const stock = Math.round((capacity * occupancy) / 100);
      return {
        id: `notif_${d.districtId.toLowerCase()}`,
        district_id: d.districtId,
        district_name: d.districtName,
        kannada_name: d.kannadaName,
        region: d.region,
        crop: d.crop,
        risk_level: d.riskLevel,
        current_viability: d.currentViability,
        predicted_viability: d.predictedViability,
        stock_tons: stock,
        capacity_tons: capacity,
        occupancy_pct: occupancy,
        moisture_risk: d.moistureVulnerability,
        facility: "Regional Grain & Seed Silo Complex",
        title: d.riskLevel === "CRITICAL" 
          ? `🚨 Critical Viability: ${d.districtName} (${d.kannadaName})`
          : d.riskLevel === "WARNING"
          ? `⚠️ Moisture Risk Alert: ${d.districtName} (${d.kannadaName})`
          : `📊 Storage & Buffer: ${d.districtName} (${d.kannadaName})`,
        message: d.earlyWarning || `Real-time seed storage telemetry for ${d.districtName}. Viability monitored at ${d.currentViability}%.`,
        recommended_action: d.recommendedAction || "Monitor seed moisture and storage conditions.",
        time_ago: "Just now",
        redistribution_eligible: d.riskLevel === "STABLE"
      };
    });

    setNotifications(fallbackList);
    setAlertCounts({
      critical: fallbackList.filter(n => n.risk_level === "CRITICAL").length,
      warning: fallbackList.filter(n => n.risk_level === "WARNING").length,
      total: fallbackList.length
    });
    const now = new Date();
    setLastSyncFormatted(now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));
    setIsSyncing(false);
  }, []);

  // Check and close drawer, keeping it closed and muting badge till next sync
  const handleCheckAndClose = useCallback((showToastNotice = false) => {
    setShowNotifications(false);
    setHasUnread(false);
    const syncTime = currentSyncBatchTime || new Date().toISOString();
    if (typeof window !== "undefined") {
      localStorage.setItem(CHECKED_SYNC_KEY, syncTime);
    }
    if (showToastNotice) {
      toast.info("Notifications checked", {
        description: "Alerts muted until new 5-minute telemetry arrives."
      });
    }
  }, [currentSyncBatchTime]);

  // Click outside listener: close panel & mark as checked
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        showNotifications &&
        panelRef.current &&
        !panelRef.current.contains(event.target as Node) &&
        bellButtonRef.current &&
        !bellButtonRef.current.contains(event.target as Node)
      ) {
        handleCheckAndClose(false);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [showNotifications, handleCheckAndClose]);

  // Initial fetch and 5-minute interval (300,000 ms)
  useEffect(() => {
    fetchLiveNotifications();
    const interval = setInterval(() => {
      fetchLiveNotifications();
    }, 300000);

    return () => clearInterval(interval);
  }, [fetchLiveNotifications]);

  // 1-second countdown clock for live 5-minute timer
  useEffect(() => {
    const timer = setInterval(() => {
      setCountdown(prev => {
        if (prev <= 1) {
          fetchLiveNotifications();
          return 300;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(timer);
  }, [fetchLiveNotifications]);

  const formatCountdown = (seconds: number) => {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}:${s < 10 ? "0" : ""}${s}`;
  };

  const toggleNotifications = () => {
    if (showNotifications) {
      handleCheckAndClose(false);
    } else {
      setShowNotifications(true);
    }
  };

  const handleSelectAlert = (districtId: string) => {
    handleCheckAndClose(false);
    
    // Dispatch global event for Karnataka Map component
    if (typeof window !== "undefined") {
      window.dispatchEvent(
        new CustomEvent("seediq:select-district", {
          detail: { districtId }
        })
      );

      // Smooth scroll to map
      const mapElem = document.getElementById("karnataka-map-section");
      if (mapElem) {
        mapElem.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    }
  };

  return (
    <header className="sticky top-0 z-30 flex items-center justify-between gap-3 border-b border-white/5 bg-black/40 backdrop-blur-xl px-4 sm:px-6 py-3">
      <div className="flex items-center gap-3">
        {/* Mobile Navigation Trigger & Brand for screens < lg */}
        <div className="flex lg:hidden items-center gap-2">
          <button
            type="button"
            onClick={onOpenMobileMenu}
            className="flex items-center justify-center h-8 w-8 rounded-lg border border-white/10 bg-white/5 text-white/80 hover:text-emerald-400 hover:bg-white/10 active:scale-95 transition cursor-pointer"
            aria-label="Open mobile menu"
          >
            <Menu className="h-4.5 w-4.5" />
          </button>
          <div className="flex items-center gap-1.5">
            <span className="font-display text-sm font-bold text-white tracking-tight">
              Seed<span className="text-emerald-400">IQ</span>
            </span>
            <span className="text-[9px] font-mono uppercase text-emerald-400/80 border border-emerald-500/20 bg-emerald-500/10 px-1.5 py-0.5 rounded">
              {user?.role || "Farmer"}
            </span>
          </div>
        </div>

        {/* Desktop title */}
        <span className="hidden text-xs uppercase tracking-[0.3em] text-white/50 lg:inline flex items-center gap-1.5">
          <span className="text-emerald-400">◆</span>
          <span>SeedIQ — 5-Minute Real-Time Karnataka Seed & Crop Storage Intelligence</span>
        </span>
      </div>

      <div className="flex items-center gap-2 sm:gap-3 relative">
        {/* Guest 5-Minute Warning Badge in Topbar */}
        {user?.isGuest && (
          <div className="flex items-center gap-2 rounded-full border border-amber-500/40 bg-amber-950/40 px-2.5 sm:px-3 py-1 sm:py-1.5 text-xs text-amber-300 font-mono shadow-[0_0_12px_rgba(245,158,11,0.2)]">
            <Clock className="h-3.5 w-3.5 text-amber-400 animate-pulse" />
            <span className="font-bold text-[11px] sm:text-xs">Guest: {formatGuestTime(guestTimeRemaining)}</span>
          </div>
        )}

        {/* 5-Minute Real-Time Storage Sync Pill */}
        <div 
          onClick={() => fetchLiveNotifications(true)}
          title="Click to sync live storage data now"
          className="flex items-center gap-1.5 sm:gap-2 rounded-full border border-emerald-500/30 bg-emerald-950/40 px-2.5 sm:px-3 py-1 sm:py-1.5 text-xs font-mono text-emerald-300 cursor-pointer hover:bg-emerald-900/40 hover:border-emerald-400 transition"
        >
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
          </span>
          <span className="hidden sm:inline text-emerald-400 font-semibold">5M LIVE SYNC:</span>
          <span className="text-white font-bold">{formatCountdown(countdown)}</span>
          <RefreshCw className={`h-3 w-3 text-emerald-400/80 ${isSyncing ? "animate-spin" : ""}`} />
        </div>

        <div className="hidden xl:flex items-center gap-2 rounded-full border border-white/5 bg-white/5 px-3 py-1.5 text-xs text-white">
          <CloudSun className="h-3.5 w-3.5 text-emerald-400" />
          <span className="font-medium">27°C</span>
          <span className="text-white/50">Karnataka Agro-Net</span>
        </div>

        <div className="hidden md:flex items-center gap-2 rounded-full border border-emerald-500/20 bg-emerald-500/10 px-3 py-1.5 text-xs">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse shadow-[0_0_8px_hsl(150_70%_45%)]" />
          <span className="font-medium text-emerald-400">STORAGE AI</span>
          <span className="text-emerald-400/60">ONLINE</span>
        </div>
        
        {/* Notification Bell with Dynamic Count Badge (Max 21, Muted after Checking) */}
        <button 
          ref={bellButtonRef}
          onClick={toggleNotifications}
          className={`relative rounded-full border p-2 transition ${
            showNotifications 
              ? 'border-emerald-500/50 bg-emerald-500/20 text-emerald-400' 
              : hasUnread && alertCounts.critical > 0
              ? 'border-red-500/40 bg-red-950/30 text-red-400 shadow-[0_0_12px_rgba(239,68,68,0.3)]'
              : hasUnread && alertCounts.total > 0
              ? 'border-amber-500/40 bg-amber-950/30 text-amber-400'
              : 'border-white/5 bg-white/5 text-white/60 hover:text-emerald-400 hover:border-emerald-500/30'
          }`} 
          aria-label="notifications"
        >
          <Bell className={`h-4 w-4 ${hasUnread && alertCounts.critical > 0 ? "animate-bounce" : ""}`} />
          {hasUnread && notifications.length > 0 && (
            <span className={`absolute -right-1 -top-1 grid h-4 w-4 place-items-center rounded-full font-display text-[9px] font-bold text-white shadow-md ${
              alertCounts.critical > 0
                ? "bg-red-500 shadow-[0_0_10px_rgba(239,68,68,0.8)]"
                : alertCounts.warning > 0
                ? "bg-amber-500"
                : "bg-emerald-500"
            }`}>
              {notifications.length}
            </span>
          )}
        </button>

        {/* 5-Minute District Seed & Crop Storage Live Panel (ONE PART ONLY - MAX 21) */}
        <AnimatePresence>
          {showNotifications && (
            <motion.div
              ref={panelRef}
              initial={{ opacity: 0, y: 10, scale: 0.95 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="absolute right-0 top-full mt-2 w-[470px] max-w-[95vw] rounded-3xl border border-emerald-500/30 bg-[#06100b]/98 p-5 shadow-[0_25px_80px_rgba(0,0,0,0.95)] backdrop-blur-2xl z-50 text-slate-100 max-h-[85vh] flex flex-col"
            >
              {/* Header (No Tabs - One Unified Part) */}
              <div className="mb-3 border-b border-white/10 pb-3">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2.5 min-w-0">
                    <div className="h-8 w-8 rounded-xl bg-emerald-500/20 border border-emerald-500/40 grid place-items-center text-emerald-400 shrink-0">
                      <Warehouse className="h-4 w-4" />
                    </div>
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <h3 className="font-display text-xs font-bold uppercase tracking-wider text-white truncate">
                          Karnataka Real-Time Alerts
                        </h3>
                        <span className="rounded-full bg-emerald-500/20 px-2 py-0.5 text-[10px] font-mono font-bold text-emerald-300 border border-emerald-500/30 shrink-0">
                          {notifications.length} Active (Max 21)
                        </span>
                      </div>
                      <p className="text-[11px] text-muted-foreground mt-0.5 font-mono truncate">
                        5-Min Sync · Refreshed: {lastSyncFormatted || "Just now"} · Next: {formatCountdown(countdown)}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    <button
                      onClick={() => fetchLiveNotifications(true)}
                      className="p-1.5 rounded-xl hover:bg-white/10 text-emerald-400 border border-white/5 transition"
                      title="Refresh 5-minute data"
                    >
                      <RefreshCw className={`h-3.5 w-3.5 ${isSyncing ? "animate-spin" : ""}`} />
                    </button>
                    <button
                      onClick={() => handleCheckAndClose(true)}
                      className="px-2.5 py-1 rounded-xl bg-emerald-500/15 hover:bg-emerald-500/25 text-emerald-400 border border-emerald-500/30 transition text-[10px] font-mono font-bold flex items-center gap-1"
                      title="Mark all as checked and close till next update"
                    >
                      <CheckCheck className="h-3.5 w-3.5" />
                      <span className="hidden sm:inline">Mark Checked</span>
                    </button>
                    <button
                      onClick={() => handleCheckAndClose(false)}
                      className="p-1.5 rounded-xl hover:bg-white/10 text-slate-400 hover:text-white border border-white/5 transition"
                      title="Close notification drawer"
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>

                {/* Quick Severity Summary Bar */}
                <div className="mt-3 grid grid-cols-4 gap-1.5 text-center text-[10px] font-mono">
                  <div className="rounded-lg bg-red-950/30 border border-red-500/30 py-1 text-red-300">
                    <span className="font-bold">{alertCounts.critical}</span> Critical
                  </div>
                  <div className="rounded-lg bg-amber-950/30 border border-amber-500/30 py-1 text-amber-300">
                    <span className="font-bold">{alertCounts.warning}</span> Warning
                  </div>
                  <div className="rounded-lg bg-yellow-950/20 border border-yellow-500/20 py-1 text-yellow-300">
                    <span className="font-bold">{notifications.filter(n => n.risk_level === "MONITOR").length}</span> Monitor
                  </div>
                  <div className="rounded-lg bg-emerald-950/30 border border-emerald-500/30 py-1 text-emerald-300">
                    <span className="font-bold">{notifications.filter(n => n.risk_level === "STABLE").length}</span> Buffer
                  </div>
                </div>
              </div>

              {/* ONE PART ONLY: Unified Single-Feed Notification Stream (Max 21 Items) */}
              <div className="space-y-2.5 overflow-y-auto pr-1 flex-1 max-h-[58vh]">
                {notifications.length === 0 ? (
                  <div className="py-8 text-center text-xs text-muted-foreground flex flex-col items-center gap-2">
                    <ShieldCheck className="h-8 w-8 text-emerald-400" />
                    <span>All 31 Karnataka districts operating within optimal parameters.</span>
                  </div>
                ) : (
                  notifications.slice(0, 21).map((notif, index) => {
                    const theme = getRiskColorTheme(notif.risk_level);
                    const occupancy = notif.occupancy_pct ?? Math.round((notif.stock_tons / Math.max(1, notif.capacity_tons)) * 100);
                    return (
                      <div
                        key={notif.id || notif.district_id || index}
                        onClick={() => handleSelectAlert(notif.district_id)}
                        className={`p-3 rounded-2xl border transition-all cursor-pointer group hover:scale-[1.01] ${
                          notif.risk_level === "CRITICAL"
                            ? "bg-red-950/25 border-red-500/40 hover:border-red-400 shadow-[0_0_15px_rgba(239,68,68,0.15)]"
                            : notif.risk_level === "WARNING"
                            ? "bg-amber-950/25 border-amber-500/35 hover:border-amber-400 shadow-[0_0_12px_rgba(245,158,11,0.1)]"
                            : notif.risk_level === "MONITOR"
                            ? "bg-yellow-950/20 border-yellow-500/30 hover:border-yellow-400"
                            : "bg-emerald-950/15 border-emerald-500/25 hover:border-emerald-400"
                        }`}
                      >
                        {/* Top District Row */}
                        <div className="flex items-center justify-between gap-2">
                          <div className="flex items-center gap-2 min-w-0">
                            <span className="text-[10px] font-mono text-muted-foreground font-bold">
                              #{index + 1}
                            </span>
                            <span className={`h-2 w-2 rounded-full shrink-0 ${theme.dot} ${notif.risk_level === "CRITICAL" ? "animate-ping" : ""}`} />
                            <span className={`text-[10px] font-mono font-bold uppercase tracking-wider ${theme.text}`}>
                              {notif.risk_level}
                            </span>
                            <span className="text-white font-bold text-xs truncate">
                              {notif.district_name}
                            </span>
                            <span className="text-[10px] text-muted-foreground shrink-0">
                              ({notif.kannada_name})
                            </span>
                          </div>

                          <span className="text-[10px] font-mono text-white/50 shrink-0">
                            {notif.time_ago || "Real-Time"}
                          </span>
                        </div>

                        {/* Title & Situation Message */}
                        <p className="mt-1.5 text-xs text-slate-200 font-medium leading-snug">
                          {notif.title || `Karnataka storage advisory for ${notif.district_name}`}
                        </p>
                        <p className="mt-0.5 text-[11px] text-muted-foreground leading-relaxed line-clamp-2">
                          {notif.message}
                        </p>

                        {/* Real-Time Telemetry Grid */}
                        <div className="mt-2 grid grid-cols-2 gap-1.5 text-[11px] bg-black/40 p-2 rounded-xl border border-white/5">
                          <div className="flex items-center justify-between pr-1">
                            <span className="text-muted-foreground text-[10px]">Crop:</span>
                            <span className="text-white font-medium">{notif.crop}</span>
                          </div>
                          <div className="flex items-center justify-between pl-1 border-l border-white/5">
                            <span className="text-muted-foreground text-[10px]">Stock:</span>
                            <span className="text-emerald-300 font-mono font-bold text-[10px]">
                              {notif.stock_tons.toLocaleString()}T ({occupancy}%)
                            </span>
                          </div>
                          <div className="flex items-center justify-between pr-1">
                            <span className="text-muted-foreground text-[10px]">Viability:</span>
                            <span className={`font-mono font-bold text-[10px] ${notif.current_viability < 60 ? "text-red-400" : "text-emerald-400"}`}>
                              {notif.current_viability}% {notif.predicted_viability ? `(AI: ${notif.predicted_viability}%)` : ""}
                            </span>
                          </div>
                          <div className="flex items-center justify-between pl-1 border-l border-white/5">
                            <span className="text-muted-foreground text-[10px]">Moisture:</span>
                            <span className={`font-medium text-[10px] ${notif.moisture_risk === "High" ? "text-red-400 font-bold" : "text-slate-300"}`}>
                              {notif.moisture_risk}
                            </span>
                          </div>
                        </div>

                        {/* Recommended Action Footer */}
                        <div className="mt-2 pt-1.5 border-t border-white/5 flex items-center justify-between text-[10px]">
                          <span className="font-semibold text-emerald-300 truncate pr-2">
                            {notif.recommended_action || "Maintain optimal storage parameters"}
                          </span>
                          <span className="flex items-center gap-1 text-sky-400 font-mono shrink-0 group-hover:translate-x-1 transition-transform">
                            Inspect Map <ArrowRight className="h-3 w-3" />
                          </span>
                        </div>
                      </div>
                    );
                  })
                )}
              </div>

              {/* Footer */}
              <div className="mt-3 pt-2.5 border-t border-white/10 flex items-center justify-between text-[10px] text-muted-foreground font-mono">
                <span>Displaying 21 Real-Time Karnataka Alerts</span>
                <button
                  onClick={() => handleCheckAndClose(true)}
                  className="text-emerald-400 hover:text-emerald-300 flex items-center gap-1 font-bold underline-offset-2 hover:underline transition cursor-pointer"
                >
                  <CheckCircle2 className="h-3 w-3" /> Dismiss until next 5m update
                </button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </header>
  );
}
