import type { ReactNode } from "react";
import { motion } from "framer-motion";

export function PageHeader({ eyebrow, title, subtitle, icon, actions }: {
  eyebrow?: string; title: ReactNode; subtitle?: string; icon?: ReactNode; actions?: ReactNode;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.7, ease: [0.2, 0.8, 0.2, 1] }}
      className="mb-8 flex flex-wrap items-end justify-between gap-6"
    >
      <div className="max-w-2xl">
        {eyebrow && (
          <div className="mb-3 inline-flex items-center gap-2 rounded-full glass px-3 py-1 text-[10px] font-medium uppercase tracking-[0.24em] text-secondary">
            <span className="h-1.5 w-1.5 rounded-full bg-primary animate-pulse-gold" />
            {eyebrow}
          </div>
        )}
        <h1 className="font-display text-4xl font-semibold leading-tight md:text-5xl">
          {icon && <span className="mr-3 inline-block align-middle">{icon}</span>}
          {title}
        </h1>
        {subtitle && <p className="mt-3 max-w-xl text-sm text-muted-foreground">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-3">{actions}</div>}
    </motion.div>
  );
}
