import { useEffect } from "react";
import { motion, useSpring, useTransform } from "framer-motion";

import natureImg from "@/assets/login-nature.jpg";
import quantumImg from "@/assets/login-quantum.jpg";

export function InteractiveBackground() {
  const springConfig = { damping: 30, stiffness: 90, mass: 0.8 };
  const mouseX = useSpring(0, springConfig);
  const mouseY = useSpring(0, springConfig);

  const natureX = useTransform(mouseX, [-1, 1], [15, -15]);
  const natureY = useTransform(mouseY, [-1, 1], [15, -15]);
  const quantumX = useTransform(mouseX, [-1, 1], [-15, 15]);
  const quantumY = useTransform(mouseY, [-1, 1], [-15, 15]);

  const orb1X = useTransform(mouseX, [-1, 1], [-50, 50]);
  const orb1Y = useTransform(mouseY, [-1, 1], [-50, 50]);
  const orb2X = useTransform(mouseX, [-1, 1], [70, -70]);
  const orb2Y = useTransform(mouseY, [-1, 1], [70, -70]);

  useEffect(() => {
    let ticking = false;
    const handleMouseMove = (e: MouseEvent) => {
      if (!ticking) {
        window.requestAnimationFrame(() => {
          const x = (e.clientX / window.innerWidth - 0.5) * 2;
          const y = (e.clientY / window.innerHeight - 0.5) * 2;
          mouseX.set(x);
          mouseY.set(y);
          ticking = false;
        });
        ticking = true;
      }
    };

    window.addEventListener("mousemove", handleMouseMove, { passive: true });
    return () => window.removeEventListener("mousemove", handleMouseMove);
  }, [mouseX, mouseY]);

  return (
    <div className="interactive-bg pointer-events-none fixed inset-0 -z-0 overflow-hidden contain-strict">
      {/* Background Images with Parallax & GPU Containment */}
      <motion.img 
        src={natureImg} 
        alt="" 
        loading="lazy"
        className="absolute -inset-10 left-0 h-[calc(100%+80px)] w-[calc(50%+40px)] object-cover opacity-25 contrast-110 saturate-110 gpu-accelerated"
        style={{ x: natureX, y: natureY }}
      />
      <motion.img 
        src={quantumImg} 
        alt="" 
        loading="lazy"
        className="absolute -inset-10 right-0 h-[calc(100%+80px)] w-[calc(50%+40px)] object-cover opacity-25 contrast-110 saturate-110 gpu-accelerated" 
        style={{ x: quantumX, y: quantumY }}
      />
      
      {/* Layered gradients for deep forest depth and subtle illumination */}
      <div className="absolute inset-0 bg-gradient-to-r from-[#020B06]/92 via-[#03150b]/80 to-[#020B06]/92" />
      <div className="absolute inset-0 bg-gradient-to-b from-[#020B06]/40 via-transparent to-[#020B06]" />
      
      {/* Smooth GPU-friendly glowing orbs */}
      <motion.div 
        className="absolute top-1/2 left-1/2 h-[45vh] w-[45vw] -translate-x-1/2 -translate-y-1/2 rounded-full bg-emerald-500/10 blur-3xl gpu-accelerated pointer-events-none"
        style={{ x: orb1X, y: orb1Y }}
      />
      
      <motion.div 
        className="absolute top-1/2 left-1/2 h-[35vh] w-[35vw] -translate-x-1/2 -translate-y-1/2 rounded-full bg-sky-500/10 blur-3xl gpu-accelerated pointer-events-none"
        style={{ x: orb2X, y: orb2Y }}
      />

      {/* Static corner glows */}
      <div className="absolute top-0 left-0 w-[40vw] h-[40vh] bg-emerald-400/5 blur-3xl" />
      <div className="absolute bottom-0 right-0 w-[40vw] h-[40vh] bg-sky-400/5 blur-3xl" />
    </div>
  );
}
