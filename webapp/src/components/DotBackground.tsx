"use client";

import { useState, useEffect } from "react";
import { usePathname } from "next/navigation";
import DotField from "./DotField";

const DARK  = { from: "rgba(0, 26, 87, 0.55)",  to: "rgba(47,95,224,0.35)"  };
const LIGHT = { from: "rgba(30,70,200,0.30)",   to: "rgba(47,95,224,0.18)"  };

// Pages where the dot field must not intercept mouse events (e.g. canvas
// interactions). The field still renders and animates — just no cursor bulge.
const NO_INTERACT_PATHS = ["/graph"];

export default function DotBackground() {
  const [colors, setColors] = useState(DARK);
  const pathname = usePathname();
  const interactive = !NO_INTERACT_PATHS.includes(pathname);

  useEffect(() => {
    const sync = () => {
      const isLight = document.documentElement.getAttribute("data-vmtheme") === "light";
      setColors(isLight ? LIGHT : DARK);
    };
    sync();
    const observer = new MutationObserver(sync);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-vmtheme"] });
    return () => observer.disconnect();
  }, []);

  return (
    <div
      aria-hidden="true"
      style={{ position: "fixed", inset: 0, zIndex: 1, pointerEvents: "none" }}
    >
      <div style={{ position: "absolute", inset: 0, pointerEvents: interactive ? "auto" : "none" }}>
        <DotField
          dotRadius={1.5}
          dotSpacing={14}
          bulgeStrength={67}
          glowRadius={160}
          sparkle={false}
          waveAmplitude={0}
          cursorRadius={500}
          cursorForce={0.1}
          bulgeOnly
          gradientFrom={colors.from}
          gradientTo={colors.to}
          glowColor="transparent"
        />
      </div>
    </div>
  );
}