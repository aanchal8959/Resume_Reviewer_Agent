import type { Metadata } from "next";

import { AuthProvider } from "./components/AuthContext";
import Nav from "./components/Nav";
import "./globals.css";

export const metadata: Metadata = {
  title: "Resume Reviewer",
  description: "Your AI career team for a smarter job switch.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className="flex h-screen h-[100dvh] flex-col overflow-hidden antialiased">
        <AuthProvider>
          <Nav />
          <div className="flex min-h-0 flex-1 flex-col overflow-y-auto overflow-x-hidden">
            {children}
          </div>
        </AuthProvider>
      </body>
    </html>
  );
}
