/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  env: {
    BUILD_ID: process.env.VERCEL_GIT_COMMIT_SHA || 'dev',
  },
}

module.exports = nextConfig
