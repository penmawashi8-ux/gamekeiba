/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  env: {
    BUILD_ID: Date.now().toString(),
  },
}

module.exports = nextConfig
