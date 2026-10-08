import { useEffect, useRef } from "react"
import * as THREE from "three"

// NASA night-lights texture (public/textures/earth-night.jpg) on a slowly spinning sphere with a blue Fresnel rim.
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

    const tex = new THREE.TextureLoader().load("/textures/earth-night.jpg")
    tex.colorSpace = THREE.SRGBColorSpace
    tex.anisotropy = renderer.capabilities.getMaxAnisotropy()
    const earth = new THREE.Mesh(
      new THREE.SphereGeometry(1.5, 96, 96),
      new THREE.MeshBasicMaterial({ map: tex, color: 0xffffff }),
    )
    earth.rotation.z = THREE.MathUtils.degToRad(-15)
    scene.add(earth)

    const rim = (power: number, scale: number, side: THREE.Side) =>
      new THREE.Mesh(
        new THREE.SphereGeometry(1.5 * scale, 64, 64),
        new THREE.ShaderMaterial({
          transparent: true,
          side,
          blending: THREE.AdditiveBlending,
          depthWrite: false,
          vertexShader: "varying vec3 n; void main(){ n = normalize(normalMatrix * normal); gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.); }",
          fragmentShader: `varying vec3 n; void main(){ float f = pow(${side === THREE.BackSide ? "0.72 - dot(n, vec3(0,0,1))" : "1.0 - abs(dot(n, vec3(0,0,1)))"}, ${power.toFixed(1)}); float lit = 0.12 + 0.88 * clamp(0.45 - n.x * 0.9, 0.0, 1.0); gl_FragColor = vec4(0.3, 0.6, 1.0, 1.0) * f * lit; }`,
        }),
      )
    scene.add(rim(2.5, 1.0, THREE.FrontSide), rim(3.0, 1.18, THREE.BackSide))

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
      if (!reduce) earth.rotation.y += 0.0012
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
