import type { Metadata } from "next";

import Nav from "./components/Nav";
import "./globals.css";

export const metadata: Metadata = {
  title: "Job Switch Agent",
  description: "Your AI career team for a smarter job switch.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">
        <Nav />
        {children}
      </body>
    </html>
  );
}
