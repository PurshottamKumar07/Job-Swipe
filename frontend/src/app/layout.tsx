import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { Suspense } from "react";
import { Providers } from "./providers";
import { Sidebar } from "@/components/sidebar";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "JobSwipe — Crawl, Swipe & Apply",
  description:
    "Find, apply and track jobs — all in one place. Powered by crwlr.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <body className={`${inter.className} bg-[#0f0a1e] text-white antialiased`} suppressHydrationWarning>
        <Providers>
          <div className="flex min-h-screen">
            <Suspense fallback={<div className="w-64 bg-[#1a1130] h-screen hidden md:block" />}>
              <Sidebar />
            </Suspense>
            <main className="flex-1 overflow-y-auto pt-14 md:pt-0">
              <div className="max-w-7xl mx-auto px-4 sm:px-6 py-6">
                <Suspense fallback={<div className="h-40 animate-pulse bg-[#1a1130] rounded-xl" />}>
                  {children}
                </Suspense>
              </div>
            </main>
          </div>
        </Providers>
      </body>
    </html>
  );
}
