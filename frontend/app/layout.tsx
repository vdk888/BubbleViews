import type { Metadata } from "next";
import { Geist_Mono, Inter } from "next/font/google";
import Link from "next/link";
import { PersonaSelector } from "@/components/PersonaSelector";
import "./globals.css";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
  display: "swap",
  weight: ["400", "500", "600", "700", "800"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Bubble — Dashboard",
  description: "Bubble. Dashboard aligné sur la charte graphique officielle.",
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
      <body className={`${inter.variable} ${geistMono.variable} antialiased`}>
        <div className="min-h-screen bg-[var(--background)] flex flex-col">
          <header className="border-b border-[var(--border)] bg-white/90 backdrop-blur-sm">
            <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
              <div className="flex items-center justify-between h-16">
                <div className="flex items-center gap-4">
                  <div className="flex items-center gap-2">
                    <div className="h-9 w-9 rounded-full border-2 border-black flex items-center justify-center relative">
                      <span className="absolute h-2 w-2 rounded-full bg-black -right-2"></span>
                    </div>
                    <div>
                      <p className="text-xl font-extrabold tracking-tight text-black leading-none">
                        Bubble.
                      </p>
                      <p className="tagline leading-none text-sm">Transparence & IA</p>
                    </div>
                  </div>
                  <nav className="hidden md:flex items-center gap-6 ml-8">
                    {navigation.map((item) => (
                      <Link
                        key={item.name}
                        href={item.href}
                        className="text-sm font-semibold text-[var(--text-secondary)] hover:text-[var(--primary)] transition-colors"
                      >
                        {item.name}
                      </Link>
                    ))}
                  </nav>
                </div>
                <div className="flex items-center gap-3">
                  <PersonaSelector />
                  <Link
                    href="/settings"
                    className="soft-button text-sm hidden sm:inline-flex"
                  >
                    Préférences
                  </Link>
                </div>
              </div>
            </div>
          </header>

          <main className="flex-1">{children}</main>

          <footer className="border-t border-[var(--border)] bg-white">
            <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
              <p className="text-center text-sm text-[var(--text-secondary)]">
                Bubble. Dashboard — identité alignée avec la charte graphique officielle.
              </p>
            </div>
          </footer>
        </div>
      </body>
    </html>
  );
}
