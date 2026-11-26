// Launch and Learn follow the portfolio API. coming_next marks readiness or retro
// "live" only when that module has real stored data. Otherwise the stage is not started
// and does not link. The date-based plan/build/verify statuses stay as the API sent them.
import type { Tag } from "@/lib/front";

export const NOT_STARTED = "not started";

export type ModuleState = { live: boolean; href: string | null };

export type LaunchLearn = { launch: ModuleState; learn: ModuleState };

type Coming = { module: string; status: string };

function state(isLive: boolean, href: string): ModuleState {
  return { live: isLive, href: isLive && href ? href : null };
}

/** Readiness makes Launch live; a stored retro makes Learn live. */
export function launchLearn(items: Coming[] | null | undefined, paths: { launch: string; learn: string }): LaunchLearn {
  const live = (module: string) => items?.some((item) => item.module === module && item.status === "live") ?? false;
  return {
    launch: state(live("readiness"), paths.launch),
    learn: state(live("retro"), paths.learn),
  };
}

type StageCard = { stage: string; tags: Tag[] };

/** Front-page cards. Launch and Learn tags and links come from the API; the other stages stay as written. */
export function frontStages<T extends StageCard>(stages: T[], modules: LaunchLearn): (T & { href: string | null })[] {
  return stages.map((stage) => {
    if (stage.stage === "Launch") {
      return { ...stage, tags: [statusTag(modules.launch.live)], href: modules.launch.href };
    }
    if (stage.stage === "Learn") {
      return { ...stage, tags: [statusTag(modules.learn.live)], href: modules.learn.href };
    }
    return { ...stage, href: null };
  });
}

function statusTag(isLive: boolean): Tag {
  return isLive ? { text: "Live", tone: "live" } : { text: NOT_STARTED, tone: "planned" };
}

/** Portfolio bar caption for one stage. Only Launch and Learn change with module data. */
export function stageCaption(name: string, status: string, modules: LaunchLearn): { text: string; href: string | null } {
  const key = name.toLowerCase();
  if (key === "launch" || key === "learn") {
    const mod = modules[key];
    return mod.live && mod.href
      ? { text: "Live", href: mod.href }
      : { text: NOT_STARTED, href: null };
  }
  return { text: status, href: null };
}
