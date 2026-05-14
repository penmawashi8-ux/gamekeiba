import { NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'

export function GET() {
  return NextResponse.json({ buildId: process.env.BUILD_ID ?? 'dev' })
}
