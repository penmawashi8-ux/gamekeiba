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

const LANE_H    = 50
const PAD_LEFT  = 56
const PAD_RIGHT = 48

export default function GameCanvas({ phase, horses, positions, raceRanking, countdown }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const animRef   = useRef<number>(0)
  const localAnimT = useRef<Record<string, number>>({})

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')!

    function resize() {
      canvas.width  = canvas.offsetWidth
      canvas.height = Math.max(horses.length * LANE_H + 24, 200)
    }
    resize()
    const ro = new ResizeObserver(resize)
    ro.observe(canvas)

    let lastTime = performance.now()

    function draw(now: number) {
      const dt = Math.min((now - lastTime) / 1000, 0.1)
      lastTime = now

      const W = canvas.width
      const trackW = W - PAD_LEFT - PAD_RIGHT

      // background
      ctx.fillStyle = '#1a472a'
      ctx.fillRect(0, 0, W, canvas.height)

      if (horses.length === 0) {
        ctx.fillStyle = '#fff'
        ctx.font = 'bold 16px sans-serif'
        ctx.textAlign = 'center'
        ctx.fillText('接続中...', W / 2, canvas.height / 2)
        animRef.current = requestAnimationFrame(draw)
        return
      }

      // lanes
      horses.forEach((h, i) => {
        const y = 12 + i * LANE_H
        ctx.fillStyle = i % 2 === 0 ? '#1e5c32' : '#1a4f2b'
        ctx.fillRect(PAD_LEFT, y, trackW, LANE_H - 2)

        // lane number badge
        ctx.fillStyle = h.color
        ctx.beginPath()
        ctx.arc(28, y + LANE_H / 2, 18, 0, Math.PI * 2)
        ctx.fill()
        ctx.strokeStyle = '#fff'
        ctx.lineWidth = 1.5
        ctx.stroke()
        ctx.fillStyle = needsDarkText(h.color) ? '#000' : '#fff'
        ctx.font = 'bold 14px sans-serif'
        ctx.textAlign = 'center'
        ctx.fillText(String(h.number), 28, y + LANE_H / 2 + 5)
      })

      // finish line
      ctx.strokeStyle = '#fff'
      ctx.setLineDash([5, 3])
      ctx.lineWidth = 2
      ctx.beginPath()
      ctx.moveTo(PAD_LEFT + trackW, 12)
      ctx.lineTo(PAD_LEFT + trackW, 12 + horses.length * LANE_H)
      ctx.stroke()
      ctx.setLineDash([])
      ctx.fillStyle = '#fff'
      ctx.font = '11px sans-serif'
      ctx.textAlign = 'center'
      ctx.fillText('GOAL', PAD_LEFT + trackW, 10)

      if (phase === 'betting' || phase === 'waiting') {
        // 出走表示
        horses.forEach((h, i) => {
          const y = 12 + i * LANE_H + LANE_H / 2
          drawHorse(ctx, PAD_LEFT + 24, y, h, 0)
          ctx.fillStyle = '#ccc'
          ctx.font = '11px sans-serif'
          ctx.textAlign = 'left'
          ctx.fillText(h.name, PAD_LEFT + 60, y - 5)
          ctx.fillStyle = '#aaa'
          ctx.font = '10px sans-serif'
          ctx.fillText(`${h.running_style} ${h.stars}`, PAD_LEFT + 60, y + 9)
        })

        // countdown overlay
        if (phase === 'betting' && countdown > 0) {
          const mm = String(Math.floor(countdown / 60)).padStart(2, '0')
          const ss = String(countdown % 60).padStart(2, '0')
          ctx.fillStyle = 'rgba(0,0,0,0.55)'
          ctx.fillRect(W / 2 - 80, canvas.height / 2 - 28, 160, 52)
          ctx.fillStyle = '#ffe066'
          ctx.font = 'bold 28px monospace'
          ctx.textAlign = 'center'
          ctx.fillText(`${mm}:${ss}`, W / 2, canvas.height / 2 + 10)
          ctx.fillStyle = '#ccc'
          ctx.font = '12px sans-serif'
          ctx.fillText('馬券受付中', W / 2, canvas.height / 2 - 12)
        }

      } else if (phase === 'racing') {
        horses.forEach((h, i) => {
          const pos = positions[String(h.number)]
          if (!pos) return
          const y = 12 + i * LANE_H + LANE_H / 2

          // local anim
          if (!localAnimT.current[h.number]) localAnimT.current[h.number] = 0
          if (!pos.finished) localAnimT.current[h.number] += dt * (1 + pos.progress)

          const screenX = PAD_LEFT + pos.progress * trackW
          drawHorse(ctx, screenX, y, h, localAnimT.current[h.number])

          // rank badge if finished
          if (pos.rank) {
            ctx.fillStyle = ['#FFD700', '#C0C0C0', '#CD7F32'][pos.rank - 1] ?? '#888'
            ctx.fillRect(W - PAD_RIGHT + 4, y - 12, 36, 24)
            ctx.fillStyle = '#000'
            ctx.font = 'bold 13px sans-serif'
            ctx.textAlign = 'center'
            ctx.fillText(`${pos.rank}着`, W - PAD_RIGHT + 22, y + 5)
          }
        })

        // live ranking top-3
        const finished = horses
          .filter(h => positions[String(h.number)]?.finished)
          .sort((a, b) => (positions[String(a.number)]?.rank ?? 99) - (positions[String(b.number)]?.rank ?? 99))
        if (finished.length > 0) {
          ctx.fillStyle = 'rgba(0,0,0,0.6)'
          ctx.fillRect(PAD_LEFT + 4, 14, 100, finished.length * 18 + 6)
          finished.slice(0, 3).forEach((h, i) => {
            ctx.fillStyle = h.color
            ctx.font = 'bold 12px sans-serif'
            ctx.textAlign = 'left'
            ctx.fillText(`${i + 1}着 [${h.number}] ${h.name}`, PAD_LEFT + 8, 26 + i * 18)
          })
        }

      } else if (phase === 'results') {
        horses.forEach((h, i) => {
          const rank = raceRanking.indexOf(h.number) + 1
          const y = 12 + i * LANE_H + LANE_H / 2
          const progress = rank === 1 ? 1.0 : Math.max(0.6, 1.0 - (rank - 1) * 0.04)
          const screenX = PAD_LEFT + progress * trackW
          drawHorse(ctx, screenX, y, h, 0)
          if (rank >= 1 && rank <= 3) {
            ctx.fillStyle = ['#FFD700', '#C0C0C0', '#CD7F32'][rank - 1]
            ctx.fillRect(W - PAD_RIGHT + 4, y - 12, 36, 24)
            ctx.fillStyle = '#000'
            ctx.font = 'bold 13px sans-serif'
            ctx.textAlign = 'center'
            ctx.fillText(`${rank}着`, W - PAD_RIGHT + 22, y + 5)
          }
        })
      }

      animRef.current = requestAnimationFrame(draw)
    }

    animRef.current = requestAnimationFrame(draw)
    return () => {
      cancelAnimationFrame(animRef.current)
      ro.disconnect()
    }
  }, [phase, horses, positions, raceRanking, countdown])

  return (
    <canvas
      ref={canvasRef}
      className="w-full block rounded-lg"
      style={{ height: Math.max(horses.length * LANE_H + 24, 200) }}
    />
  )
}

function drawHorse(
  ctx: CanvasRenderingContext2D,
  cx: number, cy: number,
  horse: HorseInfo,
  animT: number
) {
  const col    = horse.color
  const dark   = darken(col)
  const legFwd = Math.sin(animT * 14) * 8
  const legBwd = -legFwd

  ctx.save()

  // body
  ctx.fillStyle = col
  ctx.beginPath()
  ctx.ellipse(cx, cy, 26, 11, 0, 0, Math.PI * 2)
  ctx.fill()
  ctx.strokeStyle = dark
  ctx.lineWidth = 1
  ctx.stroke()

  // neck + head
  ctx.fillStyle = col
  ctx.beginPath()
  ctx.moveTo(cx + 20, cy - 10)
  ctx.lineTo(cx + 28, cy - 26)
  ctx.lineTo(cx + 40, cy - 22)
  ctx.lineTo(cx + 42, cy - 9)
  ctx.fill()
  ctx.beginPath()
  ctx.arc(cx + 40, cy - 17, 9, 0, Math.PI * 2)
  ctx.fill()
  ctx.strokeStyle = dark
  ctx.stroke()

  // eye
  const bright = hexBrightness(col)
  ctx.fillStyle = bright < 80 ? '#ccc' : '#111'
  ctx.beginPath()
  ctx.arc(cx + 45, cy - 20, 2, 0, Math.PI * 2)
  ctx.fill()

  // tail
  ctx.strokeStyle = dark
  ctx.lineWidth = 2
  ctx.beginPath()
  ctx.moveTo(cx - 24, cy - 7)
  ctx.lineTo(cx - 38, cy - 17 + legFwd / 2)
  ctx.lineTo(cx - 44, cy + 4)
  ctx.stroke()

  // legs
  ctx.strokeStyle = '#5a3a1a'
  ctx.lineWidth = 2.5
  const legPairs = [
    [cx + 12, legFwd], [cx + 4, legBwd],
    [cx - 10, legBwd], [cx - 20, legFwd],
  ]
  legPairs.forEach(([lx, loff]) => {
    ctx.beginPath()
    ctx.moveTo(lx, cy + 10)
    ctx.lineTo(lx + loff * 0.6, cy + 24)
    ctx.stroke()
  })

  // number
  ctx.fillStyle = needsDarkText(col) ? '#000' : '#fff'
  ctx.font = 'bold 11px sans-serif'
  ctx.textAlign = 'center'
  ctx.fillText(String(horse.number), cx - 4, cy + 4)

  ctx.restore()
}

function hexBrightness(hex: string): number {
  const r = parseInt(hex.slice(1, 3), 16)
  const g = parseInt(hex.slice(3, 5), 16)
  const b = parseInt(hex.slice(5, 7), 16)
  return (r * 299 + g * 587 + b * 114) / 1000
}

function needsDarkText(hex: string): boolean {
  return hexBrightness(hex) > 150
}

function darken(hex: string): string {
  const r = Math.max(0, parseInt(hex.slice(1, 3), 16) - 60)
  const g = Math.max(0, parseInt(hex.slice(3, 5), 16) - 60)
  const b = Math.max(0, parseInt(hex.slice(5, 7), 16) - 60)
  return `rgb(${r},${g},${b})`
}
