import { useEffect, useRef } from 'react'
import * as THREE from 'three'
import { createNoise3D } from 'simplex-noise'

/**
 * A real 3D organic blob rendered with Three.js/WebGL - not a CSS
 * gradient or an SVG approximation. An icosahedron's vertices are
 * displaced along their normals by 3D simplex noise (sampled per-vertex,
 * animated over time), giving genuinely irregular, continuously-morphing
 * organic geometry. Lit with a physically-based glossy/clearcoat
 * material plus several colored point lights (violet key, magenta rim,
 * white top highlight) so the wavy specular highlights that trace the
 * bumps come from real 3D lighting, not a hand-painted texture.
 *
 * Self-contained: creates and tears down its own renderer/scene/RAF loop
 * in a plain useEffect (no extra React-Three-Fiber dependency), sized to
 * fill its parent element - size it via CSS on the wrapping element.
 */
export default function HeroOrb({ className = '' }) {
  const mountRef = useRef(null)

  useEffect(() => {
    const mount = mountRef.current
    if (!mount) return

    let width = mount.clientWidth || 1
    let height = mount.clientHeight || 1

    const scene = new THREE.Scene()
    const camera = new THREE.PerspectiveCamera(42, width / height, 0.1, 100)
    camera.position.set(0, 0, 4.4)

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
    renderer.setSize(width, height)
    renderer.outputColorSpace = THREE.SRGBColorSpace
    renderer.toneMapping = THREE.ACESFilmicToneMapping
    renderer.toneMappingExposure = 1.15
    mount.appendChild(renderer.domElement)

    const DETAIL = 4 // ~2562 vertices: smooth enough, cheap enough to re-displace every frame
    const geometry = new THREE.IcosahedronGeometry(1.35, DETAIL)
    const basePositions = Float32Array.from(geometry.attributes.position.array)

    const material = new THREE.MeshPhysicalMaterial({
      color: new THREE.Color(0x0d0620),
      metalness: 0.55,
      roughness: 0.3,
      clearcoat: 1,
      clearcoatRoughness: 0.14,
      emissive: new THREE.Color(0x3b0764),
      emissiveIntensity: 0.32,
    })

    const mesh = new THREE.Mesh(geometry, material)
    scene.add(mesh)

    scene.add(new THREE.AmbientLight(0x1a0b2e, 0.7))

    const keyLight = new THREE.PointLight(0xc084fc, 22, 12, 2)
    keyLight.position.set(2.4, 1.8, 2.6)
    scene.add(keyLight)

    const rimLight = new THREE.PointLight(0x7c3aed, 16, 12, 2)
    rimLight.position.set(-2.6, -1.6, -2.2)
    scene.add(rimLight)

    const topLight = new THREE.PointLight(0xf5eaff, 9, 12, 2)
    topLight.position.set(0.2, 3, 1.6)
    scene.add(topLight)

    const fillLight = new THREE.PointLight(0x5b21b6, 8, 12, 2)
    fillLight.position.set(-1.5, 2, -2.5)
    scene.add(fillLight)

    const noise3D = createNoise3D()
    const clock = new THREE.Clock()
    let frameId

    const tmpNormal = new THREE.Vector3()

    const animate = () => {
      const t = clock.getElapsedTime()
      const posAttr = geometry.attributes.position
      const arr = posAttr.array

      for (let i = 0; i < arr.length; i += 3) {
        const ox = basePositions[i]
        const oy = basePositions[i + 1]
        const oz = basePositions[i + 2]
        tmpNormal.set(ox, oy, oz).normalize()

        const n =
          noise3D(tmpNormal.x * 1.6 + t * 0.12, tmpNormal.y * 1.6 + t * 0.12, tmpNormal.z * 1.6 + t * 0.12) * 0.65 +
          noise3D(tmpNormal.x * 3.4 - t * 0.18, tmpNormal.y * 3.4 - t * 0.18, tmpNormal.z * 3.4 - t * 0.18) * 0.35

        const scale = 1 + n * 0.24
        arr[i] = ox * scale
        arr[i + 1] = oy * scale
        arr[i + 2] = oz * scale
      }
      posAttr.needsUpdate = true
      geometry.computeVertexNormals()

      mesh.rotation.y = t * 0.09
      mesh.rotation.x = Math.sin(t * 0.11) * 0.1

      renderer.render(scene, camera)
      frameId = requestAnimationFrame(animate)
    }
    animate()

    const handleResize = () => {
      width = mount.clientWidth || 1
      height = mount.clientHeight || 1
      camera.aspect = width / height
      camera.updateProjectionMatrix()
      renderer.setSize(width, height)
    }
    const ro = new ResizeObserver(handleResize)
    ro.observe(mount)

    return () => {
      cancelAnimationFrame(frameId)
      ro.disconnect()
      if (renderer.domElement.parentNode === mount) mount.removeChild(renderer.domElement)
      geometry.dispose()
      material.dispose()
      renderer.dispose()
    }
  }, [])

  return <div ref={mountRef} className={`hero-orb-canvas ${className}`} />
}
