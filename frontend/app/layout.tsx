import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import { PersonaSelector } from "@/components/PersonaSelector";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Reddit AI Agent - Dashboard",
  description: "Control panel for autonomous Reddit AI agent with belief graph and memory",
};

const navigation = [
  { name: "Dashboard", href: "/" },
  { name: "Activity", href: "/activity" },
  { name: "Beliefs", href: "/beliefs" },
  { name: "Moderation", href: "/moderation" },
  { name: "Settings", href: "/settings" },
];

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased bg-zinc-50 dark:bg-zinc-900`}
      >
        <div className="min-h-screen flex flex-col">
          {/* Header */}
          <header className="bg-white dark:bg-zinc-800 border-b border-zinc-200 dark:border-zinc-700">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
              <div className="flex items-center justify-between h-16">
                <div className="flex items-center">
                  <h1 className="text-xl font-semibold text-zinc-900 dark:text-white">
                    Reddit AI Agent
                  </h1>
                </div>
                <nav className="hidden md:flex space-x-8">
                  {navigation.map((item) => (
                    <Link
                      key={item.name}
                      href={item.href}
                      className="text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white px-3 py-2 text-sm font-medium transition-colors"
                    >
                      {item.name}
                    </Link>
                  ))}
                </nav>
                <div className="flex items-center">
                  <PersonaSelector />
                </div>
              </div>
            </div>
          </header>

          {/* Main content */}
          <main className="flex-1">
            {children}
          </main>

          {/* Footer */}
          <footer className="bg-white dark:bg-zinc-800 border-t border-zinc-200 dark:border-zinc-700">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
              <p className="text-center text-sm text-zinc-500 dark:text-zinc-400">
                Reddit AI Agent MVP - Week 4 Dashboard
              </p>
            </div>
          </footer>
        </div>
      </body>
    </html>
  );
}
