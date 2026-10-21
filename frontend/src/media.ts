import versions from "./mediaVersions.json";

export function mediaUrl(path: string): string {
  const revision = (versions as Record<string, string>)[path];
  return revision ? `${path}?v=${revision}` : path;
}

export function illustrationSources(name: "hero-cat" | "cat-register" | "cat-login") {
  const sizes = name === "cat-register" ? [[640, 640], [1280, 1024]] : [[640, 640], [1280, 1280], [1600, 1536]];
  return sizes.map(([fileWidth, actualWidth]) => `${mediaUrl(`/media/${name}-${fileWidth}.webp`)} ${actualWidth}w`).join(", ");
}
