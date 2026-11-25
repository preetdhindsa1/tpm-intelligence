// How a program is named on screen. The platform's own repository (has_lab in the API) is
// named without its release, because its "release" is a planning phase, not a version.

export function programTitle(displayName: string, release: string, hasLab?: boolean): string {
  return hasLab ? displayName : `${displayName} ${release}`;
}
