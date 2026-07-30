"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

/** 原 compound-sourcing 路由 → 湿实验交接 */
export default function CompoundSourcingRedirect() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/workflow/wetlab-handoff");
  }, [router]);
  return null;
}
