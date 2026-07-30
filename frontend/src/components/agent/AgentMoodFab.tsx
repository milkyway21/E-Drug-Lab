"use client";

import Image from "next/image";

/** Visual mood for the floating Scientist avatar */
export type AgentMood = "idle" | "waiting" | "thinking" | "outputting" | "done";

const MOOD_META: Record<
  AgentMood,
  { label: string; ring: string; glow: string; btn: string }
> = {
  idle: {
    label: "静止",
    ring: "border-slate-200",
    glow: "shadow-md shadow-slate-200/60",
    btn: "bg-white hover:border-slate-300",
  },
  waiting: {
    label: "等待",
    ring: "border-amber-300",
    glow: "shadow-lg shadow-amber-200/70",
    btn: "bg-amber-50",
  },
  thinking: {
    label: "思考",
    ring: "border-teal-400",
    glow: "shadow-lg shadow-teal-200/70",
    btn: "bg-teal-50",
  },
  outputting: {
    label: "输出",
    ring: "border-sky-400",
    glow: "shadow-lg shadow-sky-200/80",
    btn: "bg-sky-50",
  },
  done: {
    label: "已输出",
    ring: "border-emerald-400",
    glow: "shadow-lg shadow-emerald-200/80",
    btn: "bg-emerald-50",
  },
};

type Props = {
  mood: AgentMood;
  open: boolean;
  onToggle: () => void;
};

export default function AgentMoodFab({ mood, open, onToggle }: Props) {
  const meta = MOOD_META[mood];

  return (
    <button
      type="button"
      aria-label={`打开 E-Drug Lab Scientist（${meta.label}）`}
      aria-pressed={open}
      onClick={onToggle}
      className={`agent-fab fixed bottom-6 right-6 z-[60] flex h-14 w-14 items-center justify-center overflow-visible rounded-full border-2 transition-colors duration-300 ${meta.ring} ${meta.glow} ${meta.btn}`}
      data-mood={mood}
    >
      <span className={`agent-fab-ring agent-fab-ring--${mood}`} aria-hidden />
      <span className={`agent-fab-figure agent-fab-figure--${mood} overflow-hidden rounded-full`}>
        <Image
          src="/brand/atom-scientist-fab.png"
          alt=""
          width={52}
          height={52}
          className="h-[52px] w-[52px] object-cover"
          priority
        />
      </span>
      {mood !== "idle" && (
        <span className={`agent-fab-badge agent-fab-badge--${mood}`} aria-hidden />
      )}
    </button>
  );
}
