export function Gauge({ value, label, size = 160, color = "gold" }: { value: number; label?: string; size?: number; color?: "gold" | "emerald" | "quantum" }) {
  const stroke = 10;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const dash = (value / 100) * c;
  const hue = color === "gold" ? "var(--gold)" : color === "emerald" ? "var(--emerald-glow)" : "var(--quantum)";

  return (
    <div className="relative flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="hsl(var(--muted))" strokeWidth={stroke} opacity={0.3} />
        <circle
          cx={size / 2} cy={size / 2} r={r} fill="none"
          stroke={`hsl(${hue})`}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={`${dash} ${c}`}
          style={{ filter: `drop-shadow(0 0 12px hsl(${hue} / 0.6))`, transition: "stroke-dasharray 1.2s cubic-bezier(.2,.8,.2,1)" }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <div className="font-display text-3xl font-semibold" style={{ color: `hsl(${hue})` }}>{value}%</div>
        {label && <div className="mt-1 text-[10px] font-medium uppercase tracking-widest text-muted-foreground">{label}</div>}
      </div>
    </div>
  );
}
