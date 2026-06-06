/**
 * 🌀 3D Animated Orb Component
 * React Three Fiber sphere with distort material, state-based animations,
 * orbiting particles, and glow effects.
 */
import { useRef, useMemo } from 'react'
import { useFrame } from '@react-three/fiber'
import { Sphere, MeshDistortMaterial } from '@react-three/drei'
import * as THREE from 'three'

// ── Config per state ──
const STATE_CONFIG = {
  idle: {
    color: '#00d4ff',
    emissive: '#003a4d',
    distort: 0.25,
    speed: 0.8,
    scale: 0.8,
    particleColor: '#00d4ff',
    ringSpeed: 0.3,
    glowIntensity: 0.4,
  },
  listening: {
    color: '#00ff88',
    emissive: '#004d2a',
    distort: 0.4,
    speed: 2.0,
    scale: 0.9,
    particleColor: '#00ff88',
    ringSpeed: 1.0,
    glowIntensity: 0.6,
  },
  thinking: {
    color: '#ffd700',
    emissive: '#4d3f00',
    distort: 0.35,
    speed: 1.5,
    scale: 0.85,
    particleColor: '#ffd700',
    ringSpeed: 2.0,
    glowIntensity: 0.7,
  },
  speaking: {
    color: '#ff3a8a',
    emissive: '#4d0022',
    distort: 0.45,
    speed: 2.5,
    scale: 0.95,
    particleColor: '#ff3a8a',
    ringSpeed: 1.0,
    glowIntensity: 0.8,
  },
}

// ── Inner Energy Core ──
function EnergyCore({ state }) {
  const meshRef = useRef()
  const cfg = STATE_CONFIG[state] || STATE_CONFIG.idle

  useFrame((_, delta) => {
    if (meshRef.current) {
      meshRef.current.rotation.x += delta * 0.5
      meshRef.current.rotation.y += delta * 0.8
    }
  })

  return (
    <mesh ref={meshRef}>
      <icosahedronGeometry args={[0.35, 1]} />
      <meshBasicMaterial
        color={cfg.color}
        wireframe
        transparent
        opacity={0.3}
      />
    </mesh>
  )
}

// ── Orbiting Particle Ring ──
function ParticleRing({ state, radius = 1.3, count = 60 }) {
  const groupRef = useRef()
  const cfg = STATE_CONFIG[state] || STATE_CONFIG.idle

  const particles = useMemo(() => {
    const arr = []
    for (let i = 0; i < count; i++) {
      const angle = (i / count) * Math.PI * 2
      arr.push({
        angle,
        radius: radius + (Math.random() - 0.5) * 0.3,
        y: (Math.random() - 0.5) * 0.4,
        size: 0.015 + Math.random() * 0.025,
        speed: 0.8 + Math.random() * 0.4,
      })
    }
    return arr
  }, [count, radius])

  useFrame((state_r3f, delta) => {
    if (groupRef.current) {
      groupRef.current.rotation.y += delta * cfg.ringSpeed * 0.3
      groupRef.current.rotation.x = Math.sin(state_r3f.clock.elapsedTime * 0.2) * 0.1
    }
  })

  return (
    <group ref={groupRef}>
      {particles.map((p, i) => {
        const x = Math.cos(p.angle) * p.radius
        const z = Math.sin(p.angle) * p.radius
        return (
          <mesh key={i} position={[x, p.y, z]}>
            <sphereGeometry args={[p.size, 6, 6]} />
            <meshBasicMaterial
              color={cfg.particleColor}
              transparent
              opacity={0.6}
            />
          </mesh>
        )
      })}
    </group>
  )
}

// ── Outer Glow Ring ──
function GlowRing({ state, radius = 1.2 }) {
  const meshRef = useRef()
  const cfg = STATE_CONFIG[state] || STATE_CONFIG.idle

  useFrame((s) => {
    if (meshRef.current) {
      const pulse = 1 + Math.sin(s.clock.elapsedTime * 2) * 0.05
      meshRef.current.scale.set(pulse, pulse, pulse)
    }
  })

  return (
    <mesh ref={meshRef} rotation={[Math.PI / 2, 0, 0]}>
      <ringGeometry args={[radius - 0.02, radius + 0.02, 128]} />
      <meshBasicMaterial
        color={cfg.color}
        transparent
        opacity={cfg.glowIntensity * 0.4}
        side={THREE.DoubleSide}
      />
    </mesh>
  )
}

// ── Second Ring (tilted) ──
function SecondRing({ state }) {
  const meshRef = useRef()
  const cfg = STATE_CONFIG[state] || STATE_CONFIG.idle

  useFrame((s, delta) => {
    if (meshRef.current) {
      meshRef.current.rotation.z += delta * 0.2
    }
  })

  return (
    <mesh ref={meshRef} rotation={[Math.PI / 3, Math.PI / 4, 0]}>
      <ringGeometry args={[1.4, 1.44, 128]} />
      <meshBasicMaterial
        color={cfg.color}
        transparent
        opacity={cfg.glowIntensity * 0.2}
        side={THREE.DoubleSide}
      />
    </mesh>
  )
}

// ── Background Star Field ──
function StarField({ count = 300 }) {
  const positions = useMemo(() => {
    const pos = new Float32Array(count * 3)
    for (let i = 0; i < count; i++) {
      pos[i * 3] = (Math.random() - 0.5) * 30
      pos[i * 3 + 1] = (Math.random() - 0.5) * 30
      pos[i * 3 + 2] = (Math.random() - 0.5) * 30
    }
    return pos
  }, [count])

  return (
    <points>
      <bufferGeometry>
        <bufferAttribute
          attach="attributes-position"
          count={count}
          array={positions}
          itemSize={3}
        />
      </bufferGeometry>
      <pointsMaterial
        color="#00d4ff"
        size={0.04}
        transparent
        opacity={0.5}
        sizeAttenuation
      />
    </points>
  )
}

// ── Main Orb Export ──
export default function OrbCore({ state = 'idle' }) {
  const orbRef = useRef()
  const cfg = STATE_CONFIG[state] || STATE_CONFIG.idle

  useFrame((s, delta) => {
    if (orbRef.current) {
      orbRef.current.rotation.y += delta * 0.15
      // Minimal breathing for listening state, gentle for others
      const amp = state === 'listening' ? 0.002 : 0.018
      const frequency = state === 'listening' ? 0.8 : 1.5
      const breath = 1 + Math.sin(s.clock.elapsedTime * frequency) * amp
      orbRef.current.scale.setScalar(cfg.scale * breath)
    }
  })

  return (
    <group>
      {/* Stars */}
      <StarField />

      {/* Glow Rings */}
      <GlowRing state={state} radius={2.5} />
      <SecondRing state={state} />

      {/* Particle Ring */}
      <ParticleRing state={state} />

      {/* Main Orb */}
      <Sphere ref={orbRef} args={[1, 128, 128]} scale={cfg.scale}>
        <MeshDistortMaterial
          color={cfg.color}
          emissive={cfg.emissive}
          emissiveIntensity={0.3}
          distort={cfg.distort}
          speed={cfg.speed}
          roughness={0.15}
          metalness={0.85}
          envMapIntensity={1.0}
        />
      </Sphere>

      {/* Energy Core Inside */}
      <EnergyCore state={state} />

      {/* Ambient Lights */}
      <ambientLight intensity={0.3} />
      <pointLight position={[8, 8, 8]} intensity={1.2} color="#ffffff" />
      <pointLight position={[-8, -5, -8]} intensity={0.5} color={cfg.color} />
      <pointLight position={[0, -8, 3]} intensity={0.3} color={cfg.color} />
    </group>
  )
}

export { STATE_CONFIG }