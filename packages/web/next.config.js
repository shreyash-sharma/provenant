const isDev = process.env.NODE_ENV === "development";

/** @type {import('next').NextConfig} */
const nextConfig = isDev
  ? {
      // Dev: keep Next.js SSR server so HMR works, proxy /api/* to FastAPI.
      async rewrites() {
        const api = process.env.PROVENANT_API_URL || "http://localhost:7337";
        return [{ source: "/api/:path*", destination: `${api}/api/:path*` }];
      },
    }
  : {
      // Production: export static HTML/CSS/JS.
      // FastAPI serves these files directly — no Node process needed at runtime.
      output: "export",
      images: { unoptimized: true },
    };

module.exports = nextConfig;
