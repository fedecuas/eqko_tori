import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "TORI — EQKO",
  description: "Panel de runs y aprobación de leads de TORI",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es">
      <body>
        <header className="bg-navy text-offwhite px-6 py-4">
          <h1 className="text-xl font-semibold">TORI</h1>
          <p className="text-sm text-sky">Prospección local — EQKO AIgency</p>
        </header>
        <main className="max-w-4xl mx-auto px-4 py-8">{children}</main>
      </body>
    </html>
  );
}
