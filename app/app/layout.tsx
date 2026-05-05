import type { Metadata } from "next";
import { Inter, Fraunces } from "next/font/google";
import "./globals.css";

// Inter for body / UI; Fraunces for the Verdict Card display type.
// Both are kept lean — only the weights we actually render.
const inter = Inter({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-inter",
  display: "swap",
});

const fraunces = Fraunces({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-fraunces",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Xiexie 谢谢 — your computer companion",
  description:
    "Voice-first computer-use agent for seniors. Built at the GOSIM Agentic Hackathon 2026, Paris.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${inter.variable} ${fraunces.variable}`}>
      <body className="font-[family-name:var(--font-inter)]">{children}</body>
    </html>
  );
}
