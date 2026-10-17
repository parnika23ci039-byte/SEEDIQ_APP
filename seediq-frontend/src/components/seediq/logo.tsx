export function SeedIQLogo({ size = 40 }: { size?: number }) {
  return (
    <div className="flex items-center gap-3">
      <div
        className="relative flex items-center justify-center rounded-xl bg-black/40 shadow-[0_0_20px_-5px_hsl(150_70%_45%/0.6)]"
        style={{ width: size, height: size }}
      >
        <svg viewBox="0 0 40 40" className="absolute inset-0 h-full w-full">
          <defs>
            <linearGradient id="leaf-grad" x1="0" x2="1" y1="0" y2="1">
              <stop offset="0%" stopColor="hsl(150 70% 45%)" />
              <stop offset="100%" stopColor="hsl(180 70% 40%)" />
            </linearGradient>
          </defs>
          <path
            d="M20 8 C 12 8, 8 14, 8 22 C 8 30, 14 32, 20 32 C 26 32, 32 30, 32 22 C 32 14, 28 8, 20 8 Z"
            fill="none" stroke="url(#leaf-grad)" strokeWidth="1.6"
          />
          <circle cx="20" cy="20" r="3" fill="hsl(150 70% 50%)" className="animate-pulse" />
          <circle cx="20" cy="20" r="7" fill="none" stroke="hsl(190 80% 50%)" strokeWidth="0.8" opacity="0.6" className="animate-spin" style={{ animationDuration: '4s' }} strokeDasharray="4 2" />
          <circle cx="20" cy="20" r="10" fill="none" stroke="hsl(150 70% 50%)" strokeWidth="0.5" opacity="0.4" />
        </svg>
      </div>
      <div className="leading-none">
        <div className="font-display text-lg font-bold tracking-tight text-white">
          Seed<span className="text-emerald-400">IQ</span>
        </div>
        <div className="text-[10px] font-medium uppercase tracking-widest text-emerald-400/60">
          Quantum Agriculture
        </div>
      </div>
    </div>
  );
}
