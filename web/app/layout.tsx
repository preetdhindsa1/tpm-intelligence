import type { Metadata } from "next";
import Link from "next/link";
import { AuthStatus } from "@/components/AuthStatus";
import "./globals.css";

export const metadata: Metadata = {
  title: "TPM Intelligence",
  description:
    "Open-source portfolio dashboard: release health for public Kubernetes and Apache Kafka data. Forecasts which features may slip, with ranges. Read-only for visitors; no account needed.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-slate-50 text-slate-900 antialiased">
        <header className="border-b bg-white">
          <div className="mx-auto flex max-w-[1600px] items-center justify-between px-6 py-3">
            <div className="flex items-center gap-6">
              <Link href="/" className="font-semibold">TPM Intelligence</Link>
              <nav aria-label="Main" className="flex gap-4 text-sm text-slate-600">
                <Link href="/" className="hover:text-slate-900">Overview</Link>
                <Link href="/releases" className="hover:text-slate-900">Release health</Link>
              </nav>
            </div>
            <div className="flex items-center gap-4">
              <span className="hidden text-xs text-slate-500 lg:inline">
                AI-native program health · decision support, not guarantees
              </span>
              <AuthStatus />
            </div>
          </div>
        </header>
        <main className="mx-auto max-w-[1600px] px-6 py-6">{children}</main>
      </body>
    </html>
  );
}
