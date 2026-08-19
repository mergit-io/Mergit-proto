import { useEffect, useRef } from "react";

/**
 * Animated aurora background, drawn with a hand-written WebGL fragment shader.
 *
 * Deliberately not a video and not a library: the whole thing is a few KB, stays sharp at any
 * resolution, and has no asset to license. Volumetric metaballs drift behind the hero; the CSS
 * gradient mesh underneath is the fallback if WebGL is unavailable, so the section never renders
 * blank. Honours prefers-reduced-motion by painting a single static frame.
 */

const VERT = `
attribute vec2 aPos;
void main(){ gl_Position = vec4(aPos, 0.0, 1.0); }
`;

const FRAG = `
precision highp float;
uniform vec2 uRes;
uniform float uT;

float smin(float a, float b, float k){
  float h = clamp(0.5 + 0.5*(b-a)/k, 0.0, 1.0);
  return mix(b, a, h) - k*h*(1.0-h);
}

float map(vec3 p){
  float d = 1e5;
  for(int i = 0; i < 4; i++){
    float f = float(i);
    vec3 c = vec3(
      sin(uT*0.21 + f*1.9)*2.05,
      cos(uT*0.17 + f*2.4)*0.95,
      sin(uT*0.13 + f*1.3)*1.10
    );
    d = smin(d, length(p - c) - 0.92, 1.05);
  }
  return d;
}

void main(){
  vec2 uv = (gl_FragCoord.xy*2.0 - uRes) / uRes.y;
  vec3 ro = vec3(0.0, 0.0, 6.2);
  vec3 rd = normalize(vec3(uv, -2.1));
  vec3 acc = vec3(0.0);
  float a = 0.0;
  float t = 2.0;

  for(int i = 0; i < 44; i++){
    vec3 p = ro + rd*t;
    float d = map(p);
    float dens = smoothstep(0.70, -0.30, d) * 0.085;
    if(dens > 0.0008){
      vec3 ca = vec3(0.72, 0.60, 1.00);
      vec3 cb = vec3(1.00, 0.82, 0.70);
      vec3 cc = vec3(0.66, 0.95, 0.85);
      vec3 tint = mix(mix(ca, cb, clamp(p.x*0.22 + 0.5, 0.0, 1.0)),
                      cc, clamp(p.y*0.30 + 0.42, 0.0, 1.0));
      float depth = clamp((t - 2.0) / 6.5, 0.0, 1.0);
      tint = mix(tint, vec3(1.0), depth*0.45);
      acc += (1.0 - a) * dens * tint;
      a += (1.0 - a) * dens;
    }
    t += 0.20;
    if(t > 10.5 || a > 0.96) break;
  }

  gl_FragColor = vec4(acc / max(a, 0.0015), a * 0.92);
}
`;

function compile(gl: WebGLRenderingContext, type: number, src: string): WebGLShader | null {
  const sh = gl.createShader(type);
  if (!sh) return null;
  gl.shaderSource(sh, src);
  gl.compileShader(sh);
  if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) {
    gl.deleteShader(sh);
    return null;
  }
  return sh;
}

interface Props {
  /** Extra classes for positioning/masking the canvas within its section. */
  className?: string;
}

export function GLBackground({ className = "" }: Props) {
  const ref = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;

    const gl = canvas.getContext("webgl", { antialias: false, alpha: true, premultipliedAlpha: false });
    if (!gl) return; // CSS mesh underneath remains visible

    const vs = compile(gl, gl.VERTEX_SHADER, VERT);
    const fs = compile(gl, gl.FRAGMENT_SHADER, FRAG);
    if (!vs || !fs) return;

    const prog = gl.createProgram();
    if (!prog) return;
    gl.attachShader(prog, vs);
    gl.attachShader(prog, fs);
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) return;
    gl.useProgram(prog);

    const buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    const loc = gl.getAttribLocation(prog, "aPos");
    gl.enableVertexAttribArray(loc);
    gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);

    const uRes = gl.getUniformLocation(prog, "uRes");
    const uT = gl.getUniformLocation(prog, "uT");

    const size = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
      const w = Math.max(1, Math.round(canvas.clientWidth * dpr * 0.7));
      const h = Math.max(1, Math.round(canvas.clientHeight * dpr * 0.7));
      if (canvas.width !== w || canvas.height !== h) {
        canvas.width = w;
        canvas.height = h;
      }
      gl.viewport(0, 0, canvas.width, canvas.height);
      gl.uniform2f(uRes, canvas.width, canvas.height);
    };

    const draw = (seconds: number) => {
      size();
      gl.uniform1f(uT, seconds);
      gl.clearColor(0, 0, 0, 0);
      gl.clear(gl.COLOR_BUFFER_BIT);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
    };

    const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    if (reduced) {
      draw(1.4);
      return;
    }

    let raf = 0;
    let start = 0;
    const frame = (now: number) => {
      if (!start) start = now;
      draw((now - start) / 1000);
      raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);

    const onResize = () => size();
    window.addEventListener("resize", onResize, { passive: true });

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", onResize);
      // Deliberately not calling WEBGL_lose_context: losing the context permanently poisons
      // this canvas element, so any remount — including StrictMode's double-invoke in dev —
      // would leave the hero showing the CSS mesh fallback forever.
    };
  }, []);

  return <canvas ref={ref} aria-hidden className={className} />;
}
