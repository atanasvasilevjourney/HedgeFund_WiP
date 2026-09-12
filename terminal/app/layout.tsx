import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "HedgeFund Research Terminal",
  description: "Macro regime, beta rotation, momentum engine, and crypto scanner alerts",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link
          href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
