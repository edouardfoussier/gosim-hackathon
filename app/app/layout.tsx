import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Xiexie 谢谢 — your computer companion",
  description:
    "Voice-first computer-use agent for seniors. Built at the GOSIM Agentic Hackathon 2026, Paris.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
