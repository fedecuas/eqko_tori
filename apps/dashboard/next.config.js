const path = require("path");

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Hay otro lockfile de npm en C:\Users\HP (ajeno a este proyecto) que Next.js detecta y
  // confunde con la raíz del workspace -- fijarla acá evita el warning y cualquier resolución
  // de módulos rara si alguna vez ese otro lockfile trae dependencias con nombres iguales.
  outputFileTracingRoot: path.join(__dirname),
};

module.exports = nextConfig;
