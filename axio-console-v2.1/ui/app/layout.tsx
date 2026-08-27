import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AXIO Console",
  description: "Local-first AI workspace for chat, cowork, and code.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
