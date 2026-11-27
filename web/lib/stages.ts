// Launch and Learn follow GET /portfolio (#253). Readiness stays "Live · not validated"
// unless coming_next says validated. Learn links only when this program's has_retro
// is true. A missing field, a global live flag, or a release date is not that.
import type { Tag } from "@/lib/front";

export const NO_DATA = "No data yet";
export const LIVE_UNVALIDATED = "Live · not validated";

export type ModuleState = { live: boolean; href: string | null; label: string; tone: Tag["tone"] };

export type LaunchLearn = { launch: ModuleState; learn: ModuleState };

type Coming = { module: string; status: string; validated?: boolean | null };

function idle(): ModuleState {
  return { live: false, href: null, label: NO_DATA, tone: "planned" };
}

/** `hasRetro` is the program's `has_retro`. Anything other than true does not link. */
export function launchLearn(
  items: Coming[] | null | undefined,
  paths: { launch: string; learn: string },
  hasRetro = false,
): LaunchLearn {
  const readiness = items?.find((item) => item.module === "readiness");
  const launchLive = readiness?.status === "live";
  const validated = readiness?.validated === true;
  return {
    launch: launchLive
      ? {
          live: true,
          href: paths.launch || null,
          label: validated ? "Live" : LIVE_UNVALIDATED,
          tone: validated ? "live" : "warn",
        }
      : idle(),
    learn: hasRetro && paths.learn
      ? { live: true, href: paths.learn, label: "Live", tone: "live" }
      : idle(),
  };
}

type StageCard = { stage: string; tags: Tag[]; body?: string };

/** Front-page cards. Launch and Learn tags and links come from the API; the other stages stay as written. */
export function frontStages<T extends StageCard>(stages: T[], modules: LaunchLearn): (T & { href: string | null })[] {
  return stages.map((stage) => {
    if (stage.stage === "Launch") {
      const body = modules.launch.tone === "live"
        ? "Fact-checked exec updates, and a go/no-go from the readiness signals."
        : "Fact-checked exec updates. The readiness go/no-go is not validated.";
      return { ...stage, body, tags: [{ text: modules.launch.label, tone: modules.launch.tone }], href: modules.launch.href };
    }
    if (stage.stage === "Learn") {
      return { ...stage, tags: [{ text: modules.learn.label, tone: modules.learn.tone }], href: modules.learn.href };
    }
    return { ...stage, href: null };
  });
}

/** Portfolio bar caption for one stage. Only Launch and Learn change with module data. */
export function stageCaption(name: string, status: string, modules: LaunchLearn): { text: string; href: string | null } {
  const key = name.toLowerCase();
  if (key === "launch" || key === "learn") {
    const mod = modules[key];
    return { text: mod.label, href: mod.href };
  }
  return { text: status, href: null };
}
