import type { Metadata } from "next";
import { Inter, Space_Grotesk } from "next/font/google";
import { getServerSession } from "next-auth";
import { SiteHeader } from "@/components/shell/SiteHeader";
import { authOptions, devLoginEnabled, githubEnabled, type TpmSession } from "@/lib/auth";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });
const grotesk = Space_Grotesk({ subsets: ["latin"], variable: "--font-grotesk" });

export const metadata: Metadata = {
  title: "Program Intelligence Platform",
  description:
    "AI-native program management. Every fact verified. Read-only for visitors; no account needed.",
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const session = (await getServerSession(authOptions())) as TpmSession;
  return (
    <html lang="en">
      <body className={`${inter.variable} ${grotesk.variable} min-h-screen bg-canvas font-sans text-slate-900 antialiased`}>
        <a href="#content" className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:bg-white focus:px-3 focus:py-2">
          Skip to content
        </a>
        <SiteHeader login={session?.login ?? null} signIn={githubEnabled() || devLoginEnabled()} />
        <main id="content" className="mx-auto max-w-[1600px] px-6 py-6">
          {children}
        </main>
      </body>
    </html>
  );
}
