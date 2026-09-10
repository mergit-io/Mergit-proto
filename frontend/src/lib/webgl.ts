/**
 * Whether this browser can give us a WebGL context at all.
 *
 * Asked before the 3D chunk is requested rather than after: a machine with WebGL
 * disabled, a blocked GPU driver or a locked-down browser should not download
 * half a megabyte of renderer to discover it has nowhere to put it. The probe
 * canvas is thrown away immediately — holding it would occupy one of the
 * browser's small number of live contexts for nothing.
 */
export function hasWebGL(): boolean {
  if (typeof document === "undefined") return false;
  try {
    const canvas = document.createElement("canvas");
    const context = canvas.getContext("webgl2") ?? canvas.getContext("webgl");
    const lose = (context as WebGLRenderingContext | null)?.getExtension("WEBGL_lose_context");
    lose?.loseContext();
    return Boolean(context);
  } catch {
    return false;
  }
}
