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

const LANE_H    = 52
const PAD_LEFT  = 52
const PAD_RIGHT = 44

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
      const h = stateRef.current.horses
      canvas.width  = canvas.offsetWidth
      canvas.height = Math.max(h.length * LANE_H + 20, 180)
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
        ctx.arc(26, y + LANE_H / 2, 16, 0, Math.PI * 2)
        ctx.fill()
        ctx.fillStyle = needsDark(h.color) ? '#000' : '#fff'
        ctx.font = 'bold 13px sans-serif'
        ctx.textAlign = 'center'
        ctx.fillText(String(h.number), 26, y + LANE_H / 2 + 5)
      })

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

      if (phase === 'betting' || phase === 'waiting') {
        horses.forEach((h, i) => {
          const y = 10 + i * LANE_H + LANE_H / 2
          drawHorse(ctx, PAD_LEFT + 44, y, h, 0)
          ctx.fillStyle = 'rgba(255,255,255,0.85)'
          ctx.font = '11px sans-serif'
          ctx.textAlign = 'left'
          ctx.fillText(h.name, PAD_LEFT + 98, y - 4)
          ctx.fillStyle = 'rgba(200,200,200,0.7)'
          ctx.font = '10px sans-serif'
          ctx.fillText(`${h.running_style}  ${h.stars}`, PAD_LEFT + 98, y + 10)
        })
      } else if (phase === 'racing') {
        horses.forEach((h, i) => {
          const pos = positions[String(h.number)]
          if (!pos) return
          const y = 10 + i * LANE_H + LANE_H / 2
          if (!localAnimT.current[h.number]) localAnimT.current[h.number] = 0
          if (!pos.finished) localAnimT.current[h.number] += dt * (1.5 + pos.progress * 0.5)
          drawHorse(ctx, PAD_LEFT + pos.progress * trackW, y, h, localAnimT.current[h.number])
          if (pos.rank) {
            const rc = ['#fbbf24','#9ca3af','#d97706']
            ctx.fillStyle = rc[pos.rank - 1] ?? '#6b7280'
            roundRect(ctx, W - PAD_RIGHT + 3, y - 11, 38, 22, 4); ctx.fill()
            ctx.fillStyle = '#000'; ctx.font = 'bold 12px sans-serif'; ctx.textAlign = 'center'
            ctx.fillText(`${pos.rank}着`, W - PAD_RIGHT + 22, y + 5)
          }
        })
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
            roundRect(ctx, W - PAD_RIGHT + 3, y - 11, 38, 22, 4); ctx.fill()
            ctx.fillStyle = '#000'; ctx.font = 'bold 12px sans-serif'; ctx.textAlign = 'center'
            ctx.fillText(`${rank}着`, W - PAD_RIGHT + 22, y + 5)
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
  const col = horse.color, dark = darken(col)
  const lf = Math.sin(animT * 14) * 7, lb = -lf
  ctx.save()
  ctx.fillStyle = col
  ctx.beginPath(); ctx.ellipse(cx, cy, 25, 10, 0, 0, Math.PI * 2); ctx.fill()
  ctx.strokeStyle = dark; ctx.lineWidth = 1; ctx.stroke()
  ctx.fillStyle = col
  ctx.beginPath()
  ctx.moveTo(cx+19,cy-9); ctx.lineTo(cx+27,cy-23); ctx.lineTo(cx+38,cy-19); ctx.lineTo(cx+40,cy-8)
  ctx.fill()
  ctx.beginPath(); ctx.arc(cx+38,cy-15,8,0,Math.PI*2); ctx.fill()
  ctx.strokeStyle = dark; ctx.stroke()
  ctx.fillStyle = hexBrightness(col) < 80 ? '#bbb' : '#111'
  ctx.beginPath(); ctx.arc(cx+43,cy-18,1.8,0,Math.PI*2); ctx.fill()
  ctx.strokeStyle = dark; ctx.lineWidth = 2
  ctx.beginPath(); ctx.moveTo(cx-23,cy-6); ctx.lineTo(cx-36,cy-15+lf/3); ctx.lineTo(cx-41,cy+3); ctx.stroke()
  ctx.strokeStyle = '#7c4d1e'; ctx.lineWidth = 2.5
  ;[[cx+11,lf],[cx+3,lb],[cx-9,lb],[cx-19,lf]].forEach(([lx,lo]) => {
    ctx.beginPath(); ctx.moveTo(lx,cy+9); ctx.lineTo(lx+(lo as number)*0.55,cy+22); ctx.stroke()
  })
  ctx.fillStyle = needsDark(col) ? '#000' : '#fff'
  ctx.font = 'bold 10px sans-serif'; ctx.textAlign = 'center'
  ctx.fillText(String(horse.number), cx-3, cy+4)
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
