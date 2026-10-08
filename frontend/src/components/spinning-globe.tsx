import { useEffect, useRef } from "react"
import * as THREE from "three"

// 8k day + night maps (Solar System Scope, CC BY 4.0) blended by a fixed sun on the left, so the lit limb is day and the rest shows city lights.
// The spin is a UV scroll (not a mesh rotation) so the lighting stays fixed while the planet turns.
const SUN = "normalize(vec3(-1.0, 0.25, 0.45))"

const VERT = "varying vec3 n; varying vec2 uv_; void main(){ n = normalize(normalMatrix * normal); uv_ = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.); }"

const EARTH_FRAG = `
uniform sampler2D day; uniform sampler2D night; uniform float spin;
varying vec3 n; varying vec2 uv_;
void main(){
  vec2 uv = vec2(uv_.x + spin, uv_.y);
  float d = dot(normalize(n), ${SUN});
  float k = smoothstep(-0.12, 0.3, d);
  vec3 dayC = texture2D(day, uv).rgb * (0.25 + 0.9 * max(d, 0.0));
  vec3 nightC = texture2D(night, uv).rgb * 1.6;
  vec3 c = mix(nightC, dayC, k);
  float rim = pow(1.0 - max(dot(normalize(n), vec3(0.,0.,1.)), 0.0), 3.0);
  c += vec3(0.25, 0.55, 1.0) * rim * smoothstep(-0.2, 0.7, d) * 0.9; // atmosphere only on the lit side
  gl_FragColor = vec4(c, 1.0);
}`

const GLOW_FRAG = `
varying vec3 n; varying vec2 uv_;
void main(){
  float f = pow(max(0.62 - dot(normalize(n), vec3(0.,0.,1.)), 0.0), 3.0);
  float lit = smoothstep(-0.1, 0.8, dot(normalize(n), ${SUN}));
  gl_FragColor = vec4(0.3, 0.6, 1.0, 1.0) * f * lit * 1.6;
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
    const uniforms = { day: { value: load("/textures/8k_earth_daymap.jpg") }, night: { value: load("/textures/8k_earth_nightmap.jpg") }, spin: { value: 0 } }
    const earth = new THREE.Mesh(new THREE.SphereGeometry(1.5, 128, 128), new THREE.ShaderMaterial({ uniforms, vertexShader: VERT, fragmentShader: EARTH_FRAG }))
    const glow = new THREE.Mesh(
      new THREE.SphereGeometry(1.5 * 1.16, 64, 64),
      new THREE.ShaderMaterial({ vertexShader: VERT, fragmentShader: GLOW_FRAG, side: THREE.BackSide, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false }),
    )
    scene.add(earth, glow)

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
