"use client";

import { useEffect } from "react";

/**
 * Fires the .reveal -> .reveal.in transition once per element the first time
 * it enters the viewport. Mount once per page. Reduced motion is handled by
 * the .reveal rules in globals.css, so no check is needed here.
 */
export default function RevealOnMount() {
  useEffect(() => {
    const els = document.querySelectorAll<HTMLElement>(".reveal:not(.in)");
    if (!els.length) return;
    const io = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            entry.target.classList.add("in");
            io.unobserve(entry.target);
          }
        }
      },
      { threshold: 0.1 }
    );
    els.forEach((el) => io.observe(el));
    return () => io.disconnect();
  }, []);
  return null;
}
