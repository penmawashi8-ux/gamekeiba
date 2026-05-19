'use client'

import { useRef, useEffect } from 'react'
import type { HorseInfo, HorsePosition, Phase } from '@/types/game'

interface Props {
  phase: Phase
  horses: HorseInfo[]
  positions: Record<string, HorsePosition>
  raceRanking: number[]
  countdown: number
}

const LANE_H    = 38
const PAD_LEFT  = 46
const PAD_RIGHT = 42

export default function GameCanvas({ phase, horses, positions, raceRanking, countdown }: Props) {
  const canvasRef  = useRef<HTMLCanvasElement>(null)
  const animRef    = useRef<number>(0)
  const localAnimT = useRef<Record<string, number>>({})

  const stateRef = useRef({ phase, horses, positions, raceRanking, countdown })
  useEffect(() => {
    stateRef.current = { phase, horses, positions, raceRanking, countdown }
  })

  useEffect(() => {
    const canvas = canvasRef.current as HTMLCanvasElement
    if (!canvas) return
    const ctx = canvas.getContext('2d')!

    function resize() {
      canvas.width  = canvas.offsetWidth
      canvas.height = canvas.offsetHeight
    }
    resize()
    const ro = new ResizeObserver(resize)
    ro.observe(canvas)

    let lastTime = performance.now()

    function draw(now: number) {
      const dt = Math.min((now - lastTime) / 1000, 0.1)
      lastTime = now

      const { phase, horses, positions, raceRanking } = stateRef.current
      const W      = canvas.width
      const H      = canvas.height
      const trackW = W - PAD_LEFT - PAD_RIGHT

      ctx.fillStyle = '#14532d'
      ctx.fillRect(0, 0, W, H)

      if (horses.length === 0) {
        ctx.fillStyle = 'rgba(255,255,255,0.5)'
        ctx.font = '14px sans-serif'
        ctx.textAlign = 'center'
        ctx.fillText('サーバーに接続中...', W / 2, H / 2)
        animRef.current = requestAnimationFrame(draw)
        return
      }

      horses.forEach((h, i) => {
        const y = 10 + i * LANE_H
        ctx.fillStyle = i % 2 === 0 ? '#166534' : '#15803d'
        ctx.fillRect(PAD_LEFT, y, trackW, LANE_H - 1)
        ctx.fillStyle = h.color
        ctx.beginPath()
        ctx.arc(23, y + LANE_H / 2, 13, 0, Math.PI * 2)
        ctx.fill()
        ctx.fillStyle = needsDark(h.color) ? '#000' : '#fff'
        ctx.font = 'bold 11px sans-serif'
        ctx.textAlign = 'center'
        ctx.fillText(String(h.number), 23, y + LANE_H / 2 + 4)
      })

      if (phase !== 'racing') {
        ctx.strokeStyle = 'rgba(255,255,255,0.7)'
        ctx.setLineDash([6, 4])
        ctx.lineWidth = 2
        ctx.beginPath()
        ctx.moveTo(PAD_LEFT + trackW, 10)
        ctx.lineTo(PAD_LEFT + trackW, 10 + horses.length * LANE_H)
        ctx.stroke()
        ctx.setLineDash([])
        ctx.fillStyle = 'rgba(255,255,255,0.7)'
        ctx.font = '10px sans-serif'
        ctx.textAlign = 'center'
        ctx.fillText('GOAL', PAD_LEFT + trackW, 9)
      }

      if (phase === 'betting' || phase === 'waiting') {
        horses.forEach((h, i) => {
          const y = 10 + i * LANE_H + LANE_H / 2
          ctx.fillStyle = 'rgba(255,255,255,0.92)'
          ctx.font = 'bold 11px sans-serif'
          ctx.textAlign = 'left'
          ctx.fillText(h.name, PAD_LEFT + 6, y - 3)
          ctx.fillStyle = 'rgba(180,180,180,0.75)'
          ctx.font = '9px sans-serif'
          ctx.fillText(`${h.running_style}  ${h.stars}`, PAD_LEFT + 6, y + 9)
        })
      } else if (phase === 'racing') {
        // Camera follows the pack — zooms in to 60% of track width
        const allProg = horses.map(h => positions[String(h.number)]?.progress ?? 0)
        const leadProg = Math.max(...allProg, 0.02)
        const VIEW = 0.6
        const camStart = Math.max(0, Math.min(leadProg - VIEW * 0.75, 1 - VIEW))
        const camScale = 1 / VIEW

        // Scrolling ground lines for motion feel
        const dashOff = -(now / 35) % 48
        horses.forEach((_, i) => {
          const ly = 10 + i * LANE_H + LANE_H / 2
          ctx.strokeStyle = 'rgba(255,255,255,0.07)'
          ctx.setLineDash([24, 24])
          ctx.lineDashOffset = dashOff
          ctx.lineWidth = 1
          ctx.beginPath()
          ctx.moveTo(PAD_LEFT, ly)
          ctx.lineTo(PAD_LEFT + trackW, ly)
          ctx.stroke()
        })
        ctx.setLineDash([])

        // Finish line at camera-adjusted position
        const finX = PAD_LEFT + (1.0 - camStart) * camScale * trackW
        if (finX >= PAD_LEFT && finX <= W - PAD_RIGHT + 20) {
          const fx = Math.min(finX, W - PAD_RIGHT)
          ctx.strokeStyle = 'rgba(255,255,255,0.85)'
          ctx.setLineDash([6, 4])
          ctx.lineWidth = 2
          ctx.beginPath()
          ctx.moveTo(fx, 10)
          ctx.lineTo(fx, 10 + horses.length * LANE_H)
          ctx.stroke()
          ctx.setLineDash([])
          ctx.fillStyle = 'rgba(255,255,255,0.85)'
          ctx.font = 'bold 10px sans-serif'
          ctx.textAlign = 'center'
          ctx.fillText('GOAL', fx, 9)
        }

        // Find current leader horse number
        const leaderNum = horses.reduce((best, h) => {
          const p = positions[String(h.number)]
          const bp = positions[String(best)]
          if (!p) return best
          if (!bp) return h.number
          if (p.finished && !bp.finished) return best
          if (!p.finished && bp.finished) return h.number
          if (p.rank && bp.rank) return p.rank < bp.rank ? h.number : best
          return p.progress > bp.progress ? h.number : best
        }, horses[0]?.number ?? 0)

        // Clip drawing to track area
        ctx.save()
        ctx.beginPath()
        ctx.rect(PAD_LEFT, 0, trackW, H)
        ctx.clip()

        horses.forEach((h, i) => {
          const pos = positions[String(h.number)]
          if (!pos) return
          const y = 10 + i * LANE_H + LANE_H / 2
          const screenX = PAD_LEFT + (pos.progress - camStart) * camScale * trackW
          if (screenX < PAD_LEFT - 80 || screenX > W + 20) return

          if (!localAnimT.current[h.number]) localAnimT.current[h.number] = 0
          if (!pos.finished) localAnimT.current[h.number] += dt * (3 + pos.progress * 2)

          // Leader lane glow
          if (h.number === leaderNum && !pos.finished) {
            ctx.fillStyle = 'rgba(255,210,0,0.08)'
            ctx.fillRect(PAD_LEFT, 10 + i * LANE_H, trackW, LANE_H - 1)
          }

          // Speed lines behind horse
          if (!pos.finished) {
            const t = localAnimT.current[h.number]
            ctx.lineWidth = 1.2
            for (let si = 0; si < 5; si++) {
              const phase = ((t * 2.5 + si * 0.55) % 1)
              const ly = y - 9 + si * 4.5
              const len = 18 + si * 7
              ctx.globalAlpha = (1 - phase) * 0.35 * Math.min(1, pos.progress * 4)
              ctx.strokeStyle = '#fff'
              ctx.beginPath()
              ctx.moveTo(screenX - len - phase * 35, ly)
              ctx.lineTo(screenX - phase * 35, ly)
              ctx.stroke()
            }
            ctx.globalAlpha = 1
          }

          drawHorse(ctx, screenX, y, h, localAnimT.current[h.number])
        })

        ctx.restore()

        // Rank badges (outside clip)
        horses.forEach((h, i) => {
          const pos = positions[String(h.number)]
          if (!pos?.rank) return
          const y = 10 + i * LANE_H + LANE_H / 2
          const rc = ['#fbbf24','#9ca3af','#d97706']
          ctx.fillStyle = rc[pos.rank - 1] ?? '#6b7280'
          roundRect(ctx, W - PAD_RIGHT + 2, y - 9, 36, 18, 3); ctx.fill()
          ctx.fillStyle = '#000'; ctx.font = 'bold 10px sans-serif'; ctx.textAlign = 'center'
          ctx.fillText(`${pos.rank}着`, W - PAD_RIGHT + 20, y + 4)
        })

        // Finished horses overlay
        const fin = horses
          .filter(h => positions[String(h.number)]?.finished)
          .sort((a, b) => (positions[String(a.number)]?.rank ?? 99) - (positions[String(b.number)]?.rank ?? 99))
        if (fin.length > 0) {
          ctx.fillStyle = 'rgba(0,0,0,0.55)'
          roundRect(ctx, PAD_LEFT + 4, 12, 116, fin.slice(0,3).length * 17 + 8, 6); ctx.fill()
          fin.slice(0, 3).forEach((h, i) => {
            ctx.fillStyle = h.color; ctx.font = 'bold 11px sans-serif'; ctx.textAlign = 'left'
            ctx.fillText(`${i+1}着 [${h.number}] ${h.name}`, PAD_LEFT + 10, 25 + i * 17)
          })
        }
      } else if (phase === 'results') {
        horses.forEach((h, i) => {
          const rank = raceRanking.indexOf(h.number) + 1
          const y = 10 + i * LANE_H + LANE_H / 2
          const progress = rank === 1 ? 1.0 : Math.max(0.55, 1.0 - (rank - 1) * 0.05)
          drawHorse(ctx, PAD_LEFT + progress * trackW, y, h, 0)
          if (rank >= 1 && rank <= 3) {
            const rc = ['#fbbf24','#9ca3af','#d97706']
            ctx.fillStyle = rc[rank - 1]
            roundRect(ctx, W - PAD_RIGHT + 2, y - 9, 36, 18, 3); ctx.fill()
            ctx.fillStyle = '#000'; ctx.font = 'bold 10px sans-serif'; ctx.textAlign = 'center'
            ctx.fillText(`${rank}着`, W - PAD_RIGHT + 20, y + 4)
          }
        })
      }

      animRef.current = requestAnimationFrame(draw)
    }

    animRef.current = requestAnimationFrame(draw)
    return () => { cancelAnimationFrame(animRef.current); ro.disconnect() }
  }, [])

  return (
    <canvas
      ref={canvasRef}
      className="w-full block"
      style={{ height: Math.max(horses.length * LANE_H + 20, 180), display: 'block' }}
    />
  )
}

function drawHorse(ctx: CanvasRenderingContext2D, cx: number, cy: number, horse: HorseInfo, animT: number) {
  const col = horse.color
  const dk = darken(col)
  ctx.save()
  ctx.lineCap = 'round'
  ctx.lineJoin = 'round'

  // Tail (behind body)
  const tailSway = Math.sin(animT * 14) * 5
  ctx.strokeStyle = dk
  ctx.lineWidth = 3
  ctx.beginPath()
  ctx.moveTo(cx - 19, cy - 2)
  ctx.bezierCurveTo(cx - 27, cy + 3, cx - 33, cy + 10 + tailSway, cx - 36, cy + 16 + tailSway * 1.3)
  ctx.stroke()
  ctx.lineWidth = 2
  ctx.beginPath()
  ctx.moveTo(cx - 19, cy - 2)
  ctx.bezierCurveTo(cx - 25, cy + 5, cx - 29, cy + 8 + tailSway * 0.5, cx - 31, cy + 13 + tailSway)
  ctx.stroke()

  // Legs helper (draws upper + lower segment + hoof)
  const drawLeg = (lx: number, phaseOff: number) => {
    const sw = Math.sin(animT * 14 + phaseOff) * 9
    const kx = lx + sw; const ky = cy + 15
    const hx = lx + sw * 0.5; const hy = cy + 24
    ctx.strokeStyle = dk; ctx.lineWidth = 2.5
    ctx.beginPath(); ctx.moveTo(lx, cy + 8); ctx.lineTo(kx, ky); ctx.lineTo(hx, hy); ctx.stroke()
    ctx.fillStyle = '#1a0f05'
    ctx.beginPath(); ctx.ellipse(hx, hy + 2, 3, 1.5, 0, 0, Math.PI * 2); ctx.fill()
  }

  // Back legs (drawn before body so body covers the top)
  drawLeg(cx - 9, Math.PI / 2)
  drawLeg(cx - 5, 3 * Math.PI / 2)

  // Body — three overlapping ellipses for a rounder silhouette
  ctx.fillStyle = col
  ctx.beginPath(); ctx.ellipse(cx - 12, cy - 1, 11, 9, 0.22, 0, Math.PI * 2); ctx.fill()
  ctx.beginPath(); ctx.ellipse(cx, cy, 22, 11, 0, 0, Math.PI * 2); ctx.fill()
  ctx.beginPath(); ctx.ellipse(cx + 13, cy - 1, 11, 9, -0.15, 0, Math.PI * 2); ctx.fill()
  ctx.strokeStyle = dk; ctx.lineWidth = 1.2
  ctx.beginPath(); ctx.ellipse(cx, cy, 22, 11, 0, 0, Math.PI * 2); ctx.stroke()

  // Neck (bezier filled path)
  ctx.fillStyle = col
  ctx.beginPath()
  ctx.moveTo(cx + 12, cy - 9)
  ctx.bezierCurveTo(cx + 18, cy - 17, cx + 22, cy - 24, cx + 24, cy - 27)
  ctx.lineTo(cx + 30, cy - 24)
  ctx.bezierCurveTo(cx + 27, cy - 16, cx + 22, cy - 9, cx + 18, cy - 4)
  ctx.closePath(); ctx.fill()

  // Mane
  ctx.strokeStyle = dk; ctx.lineWidth = 2.5
  ctx.beginPath()
  ctx.moveTo(cx + 26, cy - 28)
  ctx.bezierCurveTo(cx + 21, cy - 22, cx + 17, cy - 15, cx + 15, cy - 7)
  ctx.stroke()
  ctx.lineWidth = 1.5
  ctx.beginPath()
  ctx.moveTo(cx + 24, cy - 26)
  ctx.bezierCurveTo(cx + 19, cy - 20, cx + 15, cy - 14, cx + 13, cy - 7)
  ctx.stroke()

  // Head (rotated ellipse)
  ctx.fillStyle = col
  ctx.save()
  ctx.translate(cx + 34, cy - 21); ctx.rotate(0.25)
  ctx.beginPath(); ctx.ellipse(0, 0, 11, 7, 0, 0, Math.PI * 2); ctx.fill()
  ctx.strokeStyle = dk; ctx.lineWidth = 1; ctx.stroke()
  ctx.restore()

  // Muzzle / snout
  ctx.fillStyle = col
  ctx.beginPath(); ctx.ellipse(cx + 43, cy - 15, 5.5, 4, 0.3, 0, Math.PI * 2); ctx.fill()

  // Nostril
  ctx.fillStyle = dk
  ctx.beginPath(); ctx.ellipse(cx + 46, cy - 13, 1.5, 1, 0.3, 0, Math.PI * 2); ctx.fill()

  // Ear
  ctx.fillStyle = col
  ctx.beginPath()
  ctx.moveTo(cx + 28, cy - 28); ctx.lineTo(cx + 31, cy - 36); ctx.lineTo(cx + 35, cy - 28)
  ctx.closePath(); ctx.fill()
  ctx.strokeStyle = dk; ctx.lineWidth = 0.8; ctx.stroke()

  // Eye
  ctx.fillStyle = '#fff'
  ctx.beginPath(); ctx.arc(cx + 36, cy - 22, 2.2, 0, Math.PI * 2); ctx.fill()
  ctx.fillStyle = '#111'
  ctx.beginPath(); ctx.arc(cx + 36.5, cy - 22, 1.3, 0, Math.PI * 2); ctx.fill()

  // Front legs (on top of body)
  drawLeg(cx + 10, 0)
  drawLeg(cx + 6, Math.PI)

  // Jockey
  const jBob = Math.sin(animT * 14) * 1.2
  ctx.fillStyle = '#f0f0f0'
  ctx.strokeStyle = col; ctx.lineWidth = 1.5
  ctx.beginPath(); ctx.ellipse(cx + 9, cy - 15 + jBob, 8, 5, -0.4, 0, Math.PI * 2); ctx.fill(); ctx.stroke()
  // Jersey stripe
  ctx.strokeStyle = col; ctx.lineWidth = 2.5; ctx.globalAlpha = 0.75
  ctx.beginPath(); ctx.moveTo(cx + 3, cy - 17 + jBob); ctx.lineTo(cx + 14, cy - 13 + jBob); ctx.stroke()
  ctx.globalAlpha = 1
  // Head
  ctx.fillStyle = '#f5c39a'
  ctx.beginPath(); ctx.arc(cx + 17, cy - 21 + jBob, 3.8, 0, Math.PI * 2); ctx.fill()
  // Helmet
  ctx.fillStyle = col
  ctx.beginPath(); ctx.arc(cx + 17, cy - 23 + jBob, 4.3, Math.PI, 0); ctx.fill()
  ctx.fillStyle = dk
  ctx.beginPath(); ctx.rect(cx + 12.5, cy - 23.5 + jBob, 9, 1.5); ctx.fill()

  // Horse number
  ctx.fillStyle = needsDark(col) ? 'rgba(0,0,0,0.88)' : 'rgba(255,255,255,0.9)'
  ctx.font = 'bold 10px sans-serif'; ctx.textAlign = 'center'
  ctx.fillText(String(horse.number), cx - 2, cy + 5)

  ctx.restore()
}

function roundRect(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  ctx.beginPath()
  ctx.moveTo(x+r,y); ctx.lineTo(x+w-r,y); ctx.quadraticCurveTo(x+w,y,x+w,y+r)
  ctx.lineTo(x+w,y+h-r); ctx.quadraticCurveTo(x+w,y+h,x+w-r,y+h)
  ctx.lineTo(x+r,y+h); ctx.quadraticCurveTo(x,y+h,x,y+h-r)
  ctx.lineTo(x,y+r); ctx.quadraticCurveTo(x,y,x+r,y); ctx.closePath()
}
function hexBrightness(hex: string): number {
  return (parseInt(hex.slice(1,3),16)*299+parseInt(hex.slice(3,5),16)*587+parseInt(hex.slice(5,7),16)*114)/1000
}
function needsDark(hex: string): boolean { return hexBrightness(hex) > 150 }
function darken(hex: string): string {
  return `rgb(${Math.max(0,parseInt(hex.slice(1,3),16)-55)},${Math.max(0,parseInt(hex.slice(3,5),16)-55)},${Math.max(0,parseInt(hex.slice(5,7),16)-55)})`
}
