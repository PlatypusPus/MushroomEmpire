import { useEffect, useRef } from "react"
import * as THREE from "three"

// 8k day + night maps (Solar System Scope, CC BY 4.0) blended by a fixed sun on the left, so the lit limb is day and the rest shows city lights.
// The spin is a UV scroll (not a mesh rotation) so the lighting stays fixed while the planet turns.
const SUN = "normalize(vec3(-0.7, 0.3, 0.75))"

const VERT = "varying vec3 n; varying vec2 uv_; void main(){ n = normalize(normalMatrix * normal); uv_ = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.); }"

const EARTH_FRAG = `
uniform sampler2D day; uniform sampler2D night; uniform float spin;
varying vec3 n; varying vec2 uv_;
void main(){
  vec2 uv = vec2(uv_.x + spin, uv_.y);
  vec3 N = normalize(n);
  float d = dot(N, ${SUN});
  float mu = max(dot(N, vec3(0.,0.,1.)), 0.0);            // 1 at the disc centre, 0 at the limb
  vec3 dayTex = texture2D(day, uv).rgb;
  float wrap = clamp((d + 0.08) / 1.08, 0.0, 1.0);          // slightly wrapped diffuse: softer falloff toward the terminator
  vec3 dayC = dayTex * (0.04 + 1.35 * pow(wrap, 0.75)) * (0.55 + 0.45 * pow(mu, 0.4));  // limb darkening
  vec3 nightTex = texture2D(night, uv).rgb;
  float lum = dot(nightTex, vec3(0.3, 0.59, 0.11));
  vec3 nightC = vec3(lum) * 2.8 * (0.6 + 0.4 * mu) + vec3(0.006);
  float k = smoothstep(-0.14, 0.22, d);                      // day -> night blend across the terminator
  vec3 c = mix(nightC, dayC, k);
  gl_FragColor = vec4(c, 1.0);
}`

export function SpinningGlobe({ className }: { className?: string }) {
  const host = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const el = host.current!
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2))
    el.appendChild(renderer.domElement)

    const scene = new THREE.Scene()
    const camera = new THREE.PerspectiveCamera(30, 1, 0.1, 100)
    camera.position.z = 6

    const load = (url: string) => {
      const t = new THREE.TextureLoader().load(url)
      t.colorSpace = THREE.SRGBColorSpace
      t.wrapS = THREE.RepeatWrapping
      t.anisotropy = renderer.capabilities.getMaxAnisotropy()
      return t
    }
    const uniforms = { day: { value: load("/textures/8k_earth_daymap.jpg") }, night: { value: load("/textures/8k_earth_nightmap.jpg") }, spin: { value: 0.3 } }
    const earth = new THREE.Mesh(new THREE.SphereGeometry(1.5, 128, 128), new THREE.ShaderMaterial({ uniforms, vertexShader: VERT, fragmentShader: EARTH_FRAG }))
    scene.add(earth)

    const resize = () => {
      const { clientWidth: w, clientHeight: h } = el
      renderer.setSize(w, h)
      camera.aspect = w / h
      camera.updateProjectionMatrix()
    }
    resize()
    const ro = new ResizeObserver(resize)
    ro.observe(el)

    const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches
    let raf = 0
    const loop = () => {
      if (!reduce) uniforms.spin.value += 0.00018 // ~93 s per turn at 60 fps
      renderer.render(scene, camera)
      raf = requestAnimationFrame(loop)
    }
    loop()

    return () => {
      cancelAnimationFrame(raf)
      ro.disconnect()
      renderer.dispose()
      el.removeChild(renderer.domElement)
    }
  }, [])

  return <div ref={host} className={className} />
}
