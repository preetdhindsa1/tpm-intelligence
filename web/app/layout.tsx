import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "TPM Intelligence",
  description:
    "Predict which release features will slip. Plug in any cross-functional team — Kubernetes is a live example.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-slate-50 text-slate-900 antialiased">
        <header className="border-b bg-white">
          <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-3">
            <Link href="/" className="font-semibold">TPM Intelligence</Link>
            <span className="text-xs text-slate-500">
              Cross-team release intelligence · decision support, not guarantees
            </span>
          </div>
        </header>
        <main className="mx-auto max-w-7xl px-6 py-6">{children}</main>
      </body>
    </html>
  );
}
